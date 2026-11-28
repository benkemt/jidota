# 39 — Port `branch_to_pr.py` to `jidota pr collect | open`

**Depends on:** 05, 06, 07, 09, 10, 11
**Reference:** ARCHITECTURE.md §4 (BranchToPr/), §6 (Commands, Compatibility), §12 (Invariant 12);
features (decisions: `/jidota:branch-to-pr` is for branches made by hand)

## Goal

The branch-to-pr skill opens a draft PR from a branch made by hand through `jidota`, with the same
arguments, JSON output and exit codes as `branch_to_pr.py`.

## Job to do

```
jidota pr collect <source> <destination>
jidota pr open <source> <destination> --title "..." --body <file> [--dry-run]
```

1. **collect**: commits of the source missing from `origin/<destination>`, whether a push is needed,
   conflicts, an open PR of the same two branches; the tickets of those commits (subject
   `T<n> - <title> (<key>)`, a round of one, or a host squash of one), their spec, the spec's
   `(scope)` work items, the job files. Writes `context.json`, copies of the tickets and specs, in
   `.git/branch-to-pr/<source>/`, out of the working tree.
2. **open**: pushes the source branch only — never the destination, never with force — then opens
   the draft PR or updates the open one; on Azure DevOps links the `(scope)` work items.
3. Exit codes: 0 ok, 1 error, 2 nothing to propose (no commit, or a merge that changes nothing).
   JSON on stdout.
4. Uses the git, GitHub and Azure DevOps hosts of jidota (tickets 07, 09, 10) instead of importing
   `factory.py`.

> **Gap to settle**: the script finds a ticket "on the factory board, then in `specs/*/tickets/`,
> then as an issue of the `repo` of `~/.claude/spec-factory.json`". The board and that file are
> gone. Recommended order: the jobs of the jidota database (by commit subject), then
> `specs/*/tickets/`, then an issue of the issues repository of `config.json`.

## Automated tests

- `Category=Integration` (bare git origin, fake hosts): `collect` on a branch with two factory
  commits gives the JSON of the golden file recorded from `branch_to_pr.py`.
- `Category=Integration`: no commit ahead → exit 2.
- `Category=Integration`: `open` pushes only the source branch; a second `open` updates the PR.
- `Category=Unit`: `--dry-run` prints the push and the `gh` / `az` command and changes nothing.
- `Category=Unit`: ADO host links the scope work item ids.

## How to verify

On a test branch, `jidota pr collect <branch> main` then compare `context.json` with the one the
Python script writes.

## Acceptance criteria

- [ ] Same arguments, JSON and exit codes as `branch_to_pr.py`
- [ ] Only the source branch is pushed, never with force, never the destination
- [ ] Work files stay under `.git/branch-to-pr/<source>/`
- [ ] The ticket lookup order is the one chosen above
