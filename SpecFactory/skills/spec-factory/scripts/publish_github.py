#!/usr/bin/env python3
"""Publish specs/<slug>/spec.md and specs/<slug>/tickets/*.md as GitHub issues.

The spec becomes one issue; every ticket becomes an issue attached to it as a sub-issue.
With a project, every issue is also added to that GitHub Project.
Local files are updated as the publication goes: `parent_spec` and `key` in each ticket,
`child_specs` in the spec. Every created issue is recorded in published.json right away, so a
second run after a partial failure creates only what is missing.

Destination, first found: --repo / --project, the repo and project already in published.json,
~/.claude/spec-factory.json ({"repo": "owner/repo", "project": "owner/number"}), the GitHub
remote of the current folder (no project).

Usage:
    python publish_github.py --target [specs/ado-886]
    python publish_github.py specs/ado-886 --dry-run
    python publish_github.py specs/ado-886 [--repo owner/repo] [--project owner/number]

Exit codes: 0 published, 1 GitHub or CLI error, 2 invalid spec folder.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

YAML_BLOCK = re.compile(r"(```ya?ml\s*\n)(.*?)(```)", re.DOTALL)
H1 = re.compile(r"^#\s+(.+)\n?", re.MULTILINE)
TICKET_PREFIX = re.compile(r"^T\d+\s*[—–-]\s*")
SCOPE = re.compile(r"^\s*-\s*(.+?)\s*\(scope\)", re.MULTILINE)
PROJECT = re.compile(r"^([^/\s]+)/(\d+)$")
CONFIG = Path.home() / ".claude" / "spec-factory.json"


class PublishError(Exception):
    pass


class InvalidFolder(PublishError):
    pass


def gh(*args: str) -> str:
    exe = shutil.which("gh")
    if not exe:
        raise PublishError("'gh' not found on PATH")
    proc = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise PublishError(f"gh {' '.join(args[:3])} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def with_body_file(body: str, *args: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        return gh(*args, "--body-file", path)
    finally:
        os.unlink(path)


# --- markdown helpers ------------------------------------------------------

def title_of(text: str, path: Path) -> str:
    m = H1.search(text)
    if not m:
        raise InvalidFolder(f"{path}: no '# title' line")
    return m.group(1).strip()


def body_of(text: str) -> str:
    """The issue body is the file without its H1: GitHub shows the title separately."""
    return H1.sub("", text, count=1).lstrip("\n")


def set_yaml_field(text: str, name: str, value: str) -> str:
    """Set `name: value` in the first yaml block, replacing the line or appending it."""
    m = YAML_BLOCK.search(text)
    if not m:
        raise InvalidFolder(f"no yaml block to set '{name}'")
    block = m.group(2)
    line = f"{name}: {value}"
    pattern = re.compile(rf"^{re.escape(name)}:.*$", re.MULTILINE)
    block = pattern.sub(lambda _: line, block, count=1) if pattern.search(block) else block.rstrip("\n") + f"\n{line}\n"
    return text[:m.start(2)] + block + text[m.end(2):]


def yaml_field(text: str, name: str) -> str | None:
    m = YAML_BLOCK.search(text)
    f = m and re.search(rf"^{re.escape(name)}:\s*(.+)$", m.group(2), re.MULTILINE)
    return f.group(1).strip() if f else None


def spec_issue_title(spec: str, path: Path) -> str:
    """`Spec ADO #1084, #1086 — <subject>`: every scope item, grouped by tracker."""
    groups: dict[str, list[str]] = {}
    block = YAML_BLOCK.search(spec)
    for ref in SCOPE.findall(block.group(2) if block else ""):
        if m := re.search(r"ADO\s*#(\d+)", ref, re.IGNORECASE):
            groups.setdefault("ADO", []).append(f"#{m.group(1)}")
        elif m := re.search(r"(?:issues/|#)(\d+)", ref):
            groups.setdefault("GitHub", []).append(f"#{m.group(1)}")
        else:
            groups.setdefault("", []).append(ref)
    if not groups:
        raise InvalidFolder(f"{path}: no '(scope)' item in sources")
    refs = "; ".join(f"{k} {', '.join(v)}".strip() for k, v in groups.items())
    return f"Spec {refs} — {title_of(spec, path)}"


# --- publication -----------------------------------------------------------

def load(folder: Path):
    spec_path = folder / "spec.md"
    if not spec_path.is_file():
        raise InvalidFolder(f"{spec_path} not found")
    tickets = {}
    for p in sorted((folder / "tickets").glob("*.md"), key=lambda p: (len(p.stem), p.stem)):
        text = p.read_text(encoding="utf-8")
        tid = yaml_field(text, "id")
        if not tid:
            raise InvalidFolder(f"{p}: no 'id' in the yaml block")
        if tid in tickets:
            raise InvalidFolder(f"{p}: duplicate id {tid}")
        title_of(text, p)
        tickets[tid] = p
    if not tickets:
        raise InvalidFolder(f"{folder / 'tickets'}: no ticket")
    return spec_path, tickets


def save(state_path: Path, state: dict) -> None:
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def number_of(url: str) -> int:
    return int(url.rstrip("/").rsplit("/", 1)[1])


def resolve_target(state: dict, repo: str | None, project: str | None) -> tuple[str, str | None]:
    """Destination: --repo/--project, else what this folder was already published to,
    else ~/.claude/spec-factory.json, else the GitHub remote of the current folder (no project)."""
    config = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    if state.get("repo") and repo and repo != state["repo"]:
        raise PublishError(f"this folder was published to {state['repo']}, not {repo}")
    repo = repo or state.get("repo") or config.get("repo")
    if not repo:
        try:
            repo = json.loads(gh("repo", "view", "--json", "nameWithOwner"))["nameWithOwner"]
        except PublishError:
            raise PublishError(f"no GitHub repository to publish to: pass --repo owner/repo or set \"repo\" in {CONFIG}")
    project = project or state.get("project") or config.get("project")
    if project and not PROJECT.match(project):
        raise PublishError(f"project '{project}' is not <owner>/<number>, e.g. benkemt/2")
    return repo, project


def add_to_project(project: str, entry: dict, state_path: Path, state: dict) -> None:
    if entry.get("in_project"):
        return
    owner, number = PROJECT.match(project).groups()
    try:
        gh("project", "item-add", number, "--owner", owner, "--url", entry["url"])
    except PublishError as e:
        hint = " Run: gh auth refresh -s project" if "scope" in str(e) else ""
        raise PublishError(f"{e}{hint}")
    entry["in_project"] = True
    save(state_path, state)


def publish(folder: Path, repo: str | None, project: str | None, dry_run: bool) -> None:
    spec_path, tickets = load(folder)
    spec = spec_path.read_text(encoding="utf-8")
    spec_title = spec_issue_title(spec, spec_path)
    state_path = folder / "published.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    repo, project = resolve_target(state, repo, project)
    state["repo"] = repo
    if project:
        state["project"] = project
    state.setdefault("tickets", {})

    if dry_run:
        print(f"repo: {repo}")
        print(f"project: {project or 'none'}")
        print(f"spec: {'exists ' + state['spec']['url'] if 'spec' in state else 'create'} — {spec_title}")
        for tid, p in tickets.items():
            done = state["tickets"].get(tid)
            title = TICKET_PREFIX.sub("", title_of(p.read_text(encoding='utf-8'), p))
            print(f"{tid}: {'exists ' + done['url'] if done else 'create'} — {title}")
        return

    if "spec" not in state:
        url = with_body_file(body_of(spec), "issue", "create", "-R", repo, "--title", spec_title)
        state["spec"] = {"url": url, "number": number_of(url)}
        save(state_path, state)
        print(f"spec: {url}")
    spec_url, spec_number = state["spec"]["url"], state["spec"]["number"]
    if project:
        add_to_project(project, state["spec"], state_path, state)

    for tid, p in tickets.items():
        text = set_yaml_field(p.read_text(encoding="utf-8"), "parent_spec", spec_url)
        p.write_text(text, encoding="utf-8")
        done = state["tickets"].get(tid)
        if not done:
            title = TICKET_PREFIX.sub("", title_of(text, p))
            url = with_body_file(body_of(text), "issue", "create", "-R", repo, "--title", title)
            done = state["tickets"][tid] = {"url": url, "number": number_of(url), "linked": False}
            save(state_path, state)
            print(f"{tid}: {url}")
        if not done["linked"]:
            issue_id = gh("api", f"repos/{repo}/issues/{done['number']}", "--jq", ".id")
            gh("api", "-X", "POST", f"repos/{repo}/issues/{spec_number}/sub_issues", "-F", f"sub_issue_id={issue_id}")
            done["linked"] = True
            save(state_path, state)
        if project:
            add_to_project(project, done, state_path, state)
        p.write_text(set_yaml_field(text, "key", f"\"#{done['number']}\""), encoding="utf-8")

    children = ", ".join(state["tickets"][tid]["url"] for tid in tickets)
    spec = set_yaml_field(spec, "child_specs", f"[{children}]")
    spec_path.write_text(spec, encoding="utf-8")
    with_body_file(body_of(spec), "issue", "edit", str(spec_number), "-R", repo)
    print(f"done: {spec_url} with {len(tickets)} sub-issues" + (f", all in project {project}" if project else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path, nargs="?", help="spec folder, e.g. specs/ado-886")
    ap.add_argument("--repo", help="owner/repo that receives the issues")
    ap.add_argument("--project", help="GitHub Project the issues are added to, as <owner>/<number>")
    ap.add_argument("--dry-run", action="store_true", help="show what would be created, change nothing")
    ap.add_argument("--target", action="store_true", help="print the destination repo and project, change nothing")
    sys.stdout.reconfigure(encoding="utf-8")
    args = ap.parse_args()
    try:
        if args.target:
            state_path = args.folder / "published.json" if args.folder else None
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path and state_path.exists() else {}
            repo, project = resolve_target(state, args.repo, args.project)
            print(f"repo: {repo}")
            print(f"project: {project or 'none'}")
            return 0
        if not args.folder:
            ap.error("folder is required unless --target is given")
        publish(args.folder, args.repo, args.project, args.dry_run)
    except InvalidFolder as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except PublishError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
