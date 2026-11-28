# 40 — Port `workitems.py target | check` to `jidota workitems`

**Depends on:** 06, 07, 10
**Reference:** ARCHITECTURE.md §4 (WorkItems/), §6 (Commands, Compatibility), §12 (Invariant 12)

## Goal

The read and validation half of the workitems skill through `jidota`, with the same arguments,
files, JSON output and exit codes as `workitems.py`.

## Job to do

```
jidota workitems target <document> [--org <org>] [--project <project>]
jidota workitems check <document> [--sample <key>]
```

1. **target**: the Azure DevOps organization and project (arguments, else the `origin` remote —
   patterns of ticket 06), the process and its work item types, the fields of each type with their
   allowed values, the area and iteration paths, the recent backlog items. Writes `target.json` in
   `.git/workitems/<document>/`, out of the working tree.
2. **check**: validates `plan.json` against the rules of the skill and the process: hierarchy
   (Epic > Feature > User Story > Task), titles, description skeletons, acceptance criteria, story
   points, priority derivation, risk, **no tags**, Predecessor / Successor links (no cycle, none
   inside one branch), and every `file:line` cited against the repository, with the code a Task
   quotes found at the line it names. Writes `proposal.md` (`--sample` picks the item shown in
   full, default the first story) and records the fingerprint of the plan it validated.
3. Exit codes: 0 ok, 1 error, 3 the plan breaks a rule. JSON on stdout.
4. Uses the Azure DevOps host of ticket 10 instead of importing `factory.py`.

Each rule is ported from `Factory/skills/workitems/scripts/workitems.py` as written; the rules are
the contract with `skills/workitems/SKILL.md`.

## Automated tests

- `Category=Unit`, fake `az` (recorded JSON): `target.json` equals the golden file of the Python
  script.
- `Category=Unit`: one `plan.json` per rule that breaks it → exit 3 with the Python message; a
  valid plan → exit 0 and `proposal.md` equal to the golden file.
- `Category=Unit`: a Task quoting code not at its `file:line` → exit 3.
- `Category=Unit`: the fingerprint changes when `plan.json` changes by one character.

## How to verify

Run `check` with the Python script and with `jidota` on the same `plan.json`: same exit code, same
`proposal.md`.

## Acceptance criteria

- [ ] Same arguments, files, JSON and exit codes as `workitems.py target` and `check`
- [ ] Every rule of the list is enforced with the Python message
- [ ] Work files stay under `.git/workitems/<document>/`
- [ ] The fingerprint of the last clean check is recorded
