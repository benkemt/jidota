"""Tests for linear_workflow.py, with a fake Linear API. Run: python -m unittest"""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import linear_workflow as lw

SPEC = [
    {"name": "Backlog", "type": "backlog", "color": "#bec2c8", "description": "Not ready."},
    {"name": "Ready", "type": "unstarted", "color": "#e2e2e2", "description": "Approved."},
    {"name": "PR Review", "type": "started", "color": "#4cb782", "description": "PR open."},
]


def state(name, type_, position, description=None, id_=None):
    return {"id": id_ or f"id-{name}", "name": name, "type": type_, "color": "#000000",
            "position": position, "description": description}


class FakeLinear:
    """Records calls and keeps the team's statuses and issues in memory."""

    def __init__(self, states, issues=None, archive_fails=False):
        self.states = [dict(s) for s in states]
        self.issues = issues or {}  # state id -> [issue ids]
        self.archive_fails = archive_fails
        self.calls = []

    def find_team(self, ref):
        return {"id": "team-1", "key": "ABB", "name": "ABB-AU-PPO"}

    def list_states(self, team_id):
        return [dict(s) for s in self.states]

    def create_state(self, team_id, spec, position):
        self.calls.append(("create", spec["name"], spec["type"], position))
        new = state(spec["name"], spec["type"], position, spec.get("description"), id_=f"new-{spec['name']}")
        self.states.append(new)
        return new

    def update_state(self, state_id, changes):
        self.calls.append(("update", state_id, changes))
        next(s for s in self.states if s["id"] == state_id).update(changes)

    def archive_state(self, state_id):
        self.calls.append(("archive", state_id))
        if self.archive_fails:
            raise lw.LinearError("last status of its type")
        self.states = [s for s in self.states if s["id"] != state_id]

    def issues_in_state(self, state_id):
        return [{"id": i, "identifier": i} for i in self.issues.get(state_id, [])]

    def move_issue(self, issue_id, state_id):
        self.calls.append(("move", issue_id, state_id))


class PlanTest(unittest.TestCase):
    def kinds(self, actions):
        return [(a.kind, a.name) for a in actions]

    def test_matching_team_needs_nothing(self):
        current = [state(s["name"], s["type"], i, s["description"]) for i, s in enumerate(SPEC)]
        self.assertEqual(self.kinds(lw.plan(SPEC, current)), [("ok", "Backlog"), ("ok", "Ready"), ("ok", "PR Review")])

    def test_missing_status_is_created_at_its_position(self):
        current = [state("Backlog", "backlog", 0, "Not ready."), state("Ready", "unstarted", 1, "Approved.")]
        action = lw.plan(SPEC, current)[2]
        self.assertEqual((action.kind, action.name, action.position), ("create", "PR Review", 2.0))

    def test_wrong_type_is_replaced(self):
        current = [state("Backlog", "backlog", 0, "Not ready."), state("Ready", "unstarted", 1, "Approved."),
                   state("PR Review", "completed", 2, "PR open.")]
        action = lw.plan(SPEC, current)[2]
        self.assertEqual((action.kind, action.state["type"], action.spec["type"]), ("replace", "completed", "started"))

    def test_order_description_and_case_are_updated(self):
        current = [state("backlog", "backlog", 5, "old"), state("Ready", "unstarted", 1, "Approved."),
                   state("PR Review", "started", 2, "PR open.")]
        action = lw.plan(SPEC, current)[0]
        self.assertEqual(action.kind, "update")
        self.assertEqual(action.changes, {"name": "Backlog", "description": "Not ready.", "position": 0.0})

    def test_status_not_in_the_file_is_only_reported(self):
        current = [state(s["name"], s["type"], i, s["description"]) for i, s in enumerate(SPEC)]
        current.append(state("Closed", "completed", 9))
        self.assertEqual(self.kinds(lw.plan(SPEC, current))[-1], ("extra", "Closed"))

    def test_description_left_out_of_the_file_is_not_touched(self):
        spec = [{"name": "Backlog", "type": "backlog", "color": "#bec2c8"}]
        self.assertEqual(lw.plan(spec, [state("Backlog", "backlog", 0, "kept")])[0].kind, "ok")


class ApplyTest(unittest.TestCase):
    def test_replace_creates_moves_issues_then_archives(self):
        fake = FakeLinear([state("PR Review", "completed", 2, "PR open.")], issues={"id-PR Review": ["ABB-1", "ABB-2"]})
        actions = [a for a in lw.plan(SPEC, fake.list_states("team-1")) if a.name == "PR Review"]
        self.assertEqual(lw.apply(fake, "team-1", actions), [])
        self.assertEqual(fake.calls, [
            ("update", "id-PR Review", {"name": "PR Review (replaced)"}),
            ("create", "PR Review", "started", 2.0),
            ("move", "ABB-1", "new-PR Review"),
            ("move", "ABB-2", "new-PR Review"),
            ("archive", "id-PR Review"),
        ])

    def test_failed_archive_is_a_warning_not_an_error(self):
        fake = FakeLinear([state("PR Review", "completed", 2)], archive_fails=True)
        actions = [a for a in lw.plan(SPEC, fake.list_states("team-1")) if a.name == "PR Review"]
        warnings = lw.apply(fake, "team-1", actions)
        self.assertEqual(len(warnings), 1)
        self.assertIn("PR Review (replaced)", warnings[0])

    def test_extra_status_is_never_changed(self):
        fake = FakeLinear([state("Closed", "completed", 9)])
        lw.apply(fake, "team-1", [a for a in lw.plan(SPEC, fake.list_states("team-1")) if a.kind == "extra"])
        self.assertEqual(fake.calls, [])


class ConfigTest(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "workflow.toml")
            path.write_text(text, encoding="utf-8")
            return lw.load_config(path)

    def test_shipped_file_is_valid(self):
        names = [s["name"] for s in lw.load_config(lw.DEFAULT_CONFIG)]
        self.assertEqual(names, ["Backlog", "Review", "Ready", "In Progress", "Stalled", "PR Review", "Done", "Canceled", "Duplicate"])

    def test_unknown_type_is_rejected(self):
        with self.assertRaisesRegex(lw.ConfigError, "type must be"):
            self.load('[[status]]\nname = "X"\ntype = "doing"\ncolor = "#000000"\n')

    def test_duplicate_name_is_rejected(self):
        entry = '[[status]]\nname = "X"\ntype = "started"\ncolor = "#000000"\n'
        with self.assertRaisesRegex(lw.ConfigError, "duplicate name"):
            self.load(entry + entry.replace('"X"', '"x"'))


class MainTest(unittest.TestCase):
    def run_main(self, fake, *args):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(lw, "Linear", return_value=fake), \
             mock.patch.dict("os.environ", {"LINEAR_API_KEY": "test"}), \
             redirect_stdout(out), redirect_stderr(err):
            code = lw.main(["--team", "ABB", *args])
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_changes_nothing(self):
        fake = FakeLinear([state("Closed", "completed", 9)])
        code, out, _ = self.run_main(fake)
        self.assertEqual(code, 0)
        self.assertEqual(fake.calls, [])
        self.assertIn("dry run", out)
        self.assertIn("extra    Closed", out)

    def test_apply_creates_the_workflow(self):
        fake = FakeLinear([])
        code, _, _ = self.run_main(fake, "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(len([c for c in fake.calls if c[0] == "create"]), 9)

    def test_missing_api_key_stops(self):
        with mock.patch.dict("os.environ", {}, clear=True), redirect_stderr(io.StringIO()):
            self.assertEqual(lw.main(["--team", "ABB"]), 2)


if __name__ == "__main__":
    unittest.main()
