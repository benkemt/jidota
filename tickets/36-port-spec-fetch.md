# 36 — Port `fetch_source.py` to `jidota spec fetch`

**Depends on:** 07, 09
**Reference:** ARCHITECTURE.md §4 (Spec/), §6 (Commands, Compatibility), §12 (Invariant 12);
feature "JidoTa operated from one command"

## Goal

The spec factory reads its source work item through `jidota` instead of Python, with the same
inputs, outputs and exit codes, because `SKILL.md` routes on them.

## Job to do

Port `Factory/skills/spec-factory/scripts/fetch_source.py` to `jidota spec fetch`:

```
jidota spec fetch ado#1084
jidota spec fetch https://dev.azure.com/<org>/<project>/_workitems/edit/1084
jidota spec fetch gh#12
jidota spec fetch https://github.com/<owner>/<repo>/issues/12
jidota spec fetch gh#12 --root specs --force
```

- Reads the work item (ADO, through `az`; `ado#<id>` uses `az devops configure --defaults`, a full
  URL sets the organization) or the issue (GitHub, through `gh`), and its **direct** children:
  ADO children in state `New`, GitHub sub-issues that are open. Other children and links are
  listed by id and title, not read.
- Writes `specs/<slug>/source.md` (`slug` = `ado-<id>` or `gh-<number>`), in the format the Python
  script writes; prints the output folder.
- Exit codes: 0 written, 1 tracker or CLI error, 2 bad argument, 3 folder already exists (use
  `--force`).
- Runs in the owner's working copy (it is an interactive skill script, not the job loop); needs no
  running instance.

Parity: before the Python script is removed (ticket 42), record its outputs on a set of sample
inputs (a fake `az`/`gh` answer set) as golden files under `tests/Jidota.Tests/Fixtures/parity/fetch/`.

## Automated tests

- `Category=Unit`: each accepted form of the argument is parsed; an unknown form exits 2.
- `Category=Unit`, fake `az`/`gh` (recorded JSON): `source.md` equals the golden file of the
  Python script for an ADO Feature with New and Active children, and for a GitHub issue with open
  and closed sub-issues.
- `Category=Unit`: an existing folder without `--force` exits 3 and changes nothing.
- `Category=Unit`: a CLI failure exits 1.

## How to verify

`jidota spec fetch ado#<test id>` in a test repository, then compare `specs/ado-<id>/source.md` with
the one the Python script wrote for the same item.

## Acceptance criteria

- [ ] Same arguments, same `source.md`, same exit codes as `fetch_source.py`
- [ ] Only direct children are read, with the state rules above
- [ ] Golden-file parity tests run in the pipeline without `az` or `gh`
