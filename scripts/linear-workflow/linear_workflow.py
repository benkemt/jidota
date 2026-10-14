#!/usr/bin/env python3
"""Set up the JidoTa workflow statuses in a Linear team.

Reads the statuses from workflow.toml and compares them with the team's:

- a missing status is created;
- a status with the wrong order or description is updated;
- a status with the wrong type is recreated: the old one is renamed, a new one
  is created with the right type, its issues are moved, and the old one is
  archived (Linear does not change the type of an existing status);
- a status of the team that is not in the file is only reported.

Dry run by default: nothing changes without --apply.

Usage:
    LINEAR_API_KEY=lin_api_... python linear_workflow.py --team ABB
    LINEAR_API_KEY=lin_api_... python linear_workflow.py --team ABB --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

API_URL = "https://api.linear.app/graphql"
DEFAULT_CONFIG = Path(__file__).with_name("workflow.toml")
STATUS_TYPES = {"backlog", "unstarted", "started", "completed", "canceled", "duplicate"}
REPLACED_SUFFIX = " (replaced)"


class LinearError(Exception):
    pass


class ConfigError(Exception):
    pass


# --- Linear API ---------------------------------------------------------------


class Linear:
    """The few Linear GraphQL calls this script needs."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    def _call(self, query: str, variables: dict | None = None) -> dict:
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        request = urllib.request.Request(
            API_URL,
            data=body,
            headers={"Content-Type": "application/json", "Authorization": self._api_key},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:500]
            raise LinearError(f"HTTP {error.code}: {detail}") from None
        except urllib.error.URLError as error:
            raise LinearError(f"cannot reach Linear: {error.reason}") from None
        if payload.get("errors"):
            raise LinearError("; ".join(e.get("message", "unknown error") for e in payload["errors"]))
        return payload["data"]

    def find_team(self, ref: str) -> dict:
        teams, after = [], None
        while True:
            data = self._call(
                "query($after: String) { teams(first: 250, after: $after) {"
                " nodes { id key name } pageInfo { hasNextPage endCursor } } }",
                {"after": after},
            )["teams"]
            teams += data["nodes"]
            if not data["pageInfo"]["hasNextPage"]:
                break
            after = data["pageInfo"]["endCursor"]
        wanted = ref.casefold()
        for team in teams:
            if wanted in (team["id"].casefold(), team["key"].casefold(), team["name"].casefold()):
                return team
        raise LinearError(f"no team with key, name, or ID {ref!r}")

    def list_states(self, team_id: str) -> list[dict]:
        data = self._call(
            "query($id: String!) { team(id: $id) { states(first: 250) {"
            " nodes { id name type color position description } } } }",
            {"id": team_id},
        )
        return data["team"]["states"]["nodes"]

    def create_state(self, team_id: str, spec: dict, position: float) -> dict:
        state_input = {
            "teamId": team_id,
            "name": spec["name"],
            "type": spec["type"],
            "color": spec["color"],
            "position": position,
        }
        if spec.get("description") is not None:
            state_input["description"] = spec["description"]
        data = self._call(
            "mutation($input: WorkflowStateCreateInput!) { workflowStateCreate(input: $input) {"
            " success workflowState { id name type } } }",
            {"input": state_input},
        )["workflowStateCreate"]
        if not data["success"]:
            raise LinearError(f"Linear refused to create {spec['name']!r}")
        return data["workflowState"]

    def update_state(self, state_id: str, changes: dict) -> None:
        data = self._call(
            "mutation($id: String!, $input: WorkflowStateUpdateInput!) {"
            " workflowStateUpdate(id: $id, input: $input) { success } }",
            {"id": state_id, "input": changes},
        )["workflowStateUpdate"]
        if not data["success"]:
            raise LinearError(f"Linear refused to update status {state_id}")

    def archive_state(self, state_id: str) -> None:
        data = self._call(
            "mutation($id: String!) { workflowStateArchive(id: $id) { success } }",
            {"id": state_id},
        )["workflowStateArchive"]
        if not data["success"]:
            raise LinearError(f"Linear refused to archive status {state_id}")

    def issues_in_state(self, state_id: str) -> list[dict]:
        issues, after = [], None
        while True:
            data = self._call(
                "query($state: ID!, $after: String) { issues(first: 100, after: $after,"
                " includeArchived: true, filter: { state: { id: { eq: $state } } }) {"
                " nodes { id identifier } pageInfo { hasNextPage endCursor } } }",
                {"state": state_id, "after": after},
            )["issues"]
            issues += data["nodes"]
            if not data["pageInfo"]["hasNextPage"]:
                return issues
            after = data["pageInfo"]["endCursor"]

    def move_issue(self, issue_id: str, state_id: str) -> None:
        data = self._call(
            "mutation($id: String!, $input: IssueUpdateInput!) { issueUpdate(id: $id, input: $input) { success } }",
            {"id": issue_id, "input": {"stateId": state_id}},
        )["issueUpdate"]
        if not data["success"]:
            raise LinearError(f"Linear refused to move issue {issue_id}")


# --- Configuration --------------------------------------------------------------


def load_config(path: Path) -> list[dict]:
    try:
        statuses = tomllib.loads(path.read_text(encoding="utf-8")).get("status", [])
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"{path}: {error}") from None
    if not statuses:
        raise ConfigError(f"{path}: no [[status]] entry")
    seen = set()
    for index, spec in enumerate(statuses, start=1):
        where = f"{path}, status {index}"
        if not isinstance(spec.get("name"), str) or not spec["name"].strip():
            raise ConfigError(f"{where}: missing name")
        if spec.get("type") not in STATUS_TYPES:
            raise ConfigError(f"{where}: type must be one of {', '.join(sorted(STATUS_TYPES))}")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(spec.get("color", ""))):
            raise ConfigError(f"{where}: color must look like #5e6ad2")
        key = spec["name"].casefold()
        if key in seen:
            raise ConfigError(f"{where}: duplicate name {spec['name']!r}")
        seen.add(key)
    return statuses


# --- Plan ---------------------------------------------------------------------


@dataclass
class Action:
    kind: str  # "ok" | "create" | "update" | "replace" | "extra"
    spec: dict | None = None
    state: dict | None = None
    position: float = 0.0
    changes: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return (self.spec or self.state)["name"]


def plan(desired: list[dict], current: list[dict]) -> list[Action]:
    """Compare the wanted statuses with the team's. Pure: calls nothing."""
    by_name = {state["name"].casefold(): state for state in current}
    actions = []
    for index, spec in enumerate(desired):
        position = float(index)
        state = by_name.pop(spec["name"].casefold(), None)
        if state is None:
            actions.append(Action("create", spec=spec, position=position))
        elif state["type"] != spec["type"]:
            actions.append(Action("replace", spec=spec, state=state, position=position))
        else:
            changes = {}
            if state["name"] != spec["name"]:
                changes["name"] = spec["name"]
            if spec.get("description") is not None and (state.get("description") or "") != spec["description"]:
                changes["description"] = spec["description"]
            if float(state["position"]) != position:
                changes["position"] = position
            kind = "update" if changes else "ok"
            actions.append(Action(kind, spec=spec, state=state, position=position, changes=changes))
    actions += [Action("extra", state=state) for state in sorted(current, key=lambda s: s["position"]) if state["name"].casefold() in by_name]
    return actions


def describe(action: Action, issue_count: int | None = None) -> str:
    if action.kind == "ok":
        return f"ok       {action.name}"
    if action.kind == "create":
        return f"create   {action.name} ({action.spec['type']})"
    if action.kind == "update":
        return f"update   {action.name}: {', '.join(sorted(action.changes))}"
    if action.kind == "replace":
        moved = "" if issue_count is None else f", move {issue_count} issue(s)"
        return (
            f"replace  {action.name}: type {action.state['type']} -> {action.spec['type']}"
            f" (create new{moved}, archive old)"
        )
    return f"extra    {action.name} ({action.state['type']}): not in the JidoTa workflow, left as is"


# --- Apply --------------------------------------------------------------------


def apply(linear: Linear, team_id: str, actions: list[Action]) -> list[str]:
    """Carry out the plan. Returns the warnings; raises on the first hard failure."""
    warnings = []
    for action in actions:
        if action.kind == "create":
            linear.create_state(team_id, action.spec, action.position)
        elif action.kind == "update":
            linear.update_state(action.state["id"], action.changes)
        elif action.kind == "replace":
            old = action.state
            linear.update_state(old["id"], {"name": old["name"] + REPLACED_SUFFIX})
            new = linear.create_state(team_id, action.spec, action.position)
            for issue in linear.issues_in_state(old["id"]):
                linear.move_issue(issue["id"], new["id"])
            try:
                linear.archive_state(old["id"])
            except LinearError as error:
                warnings.append(
                    f"could not archive {old['name'] + REPLACED_SUFFIX!r} ({error});"
                    " its issues were moved, archive it by hand"
                )
    return warnings


# --- Command line -------------------------------------------------------------


def print_states(states: list[dict]) -> None:
    width = max((len(s["name"]) for s in states), default=0)
    for state in sorted(states, key=lambda s: (s["type"], s["position"])):
        print(f"  {state['name']:<{width}}  {state['type']:<9}  {state['id']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Set up the JidoTa workflow statuses in a Linear team.")
    parser.add_argument("--team", required=True, help="team key, name, or ID (for example ABB)")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="statuses file (default: workflow.toml)")
    parser.add_argument("--apply", action="store_true", help="make the changes (default: dry run)")
    parser.add_argument("--json", action="store_true", help="print the final statuses as JSON (name -> id, type)")
    args = parser.parse_args(argv)

    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        print("error: set LINEAR_API_KEY to a Linear personal API key", file=sys.stderr)
        return 2

    try:
        desired = load_config(args.config)
        linear = Linear(api_key)
        team = linear.find_team(args.team)
        actions = plan(desired, linear.list_states(team["id"]))

        # With --json, stdout carries only the JSON; the plan goes to stderr.
        log = sys.stderr if args.json else sys.stdout
        print(f"Team {team['name']} ({team['key']}){'' if args.apply else ' - dry run, nothing changes'}", file=log)
        for action in actions:
            count = len(linear.issues_in_state(action.state["id"])) if action.kind == "replace" else None
            print("  " + describe(action, count), file=log)

        if args.apply:
            for warning in apply(linear, team["id"], actions):
                print(f"warning: {warning}", file=sys.stderr)
        elif any(a.kind in ("create", "update", "replace") for a in actions):
            print("Run again with --apply to make these changes.", file=log)

        states = linear.list_states(team["id"])
    except (ConfigError, LinearError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({s["name"]: {"id": s["id"], "type": s["type"]} for s in states}, indent=2))
    else:
        print("Statuses:")
        print_states(states)
    return 0


if __name__ == "__main__":
    sys.exit(main())
