# 43 — Align the documentation

**Depends on:** 32, 33, 42
**Reference:** features "Documents to align when this is built"; ARCHITECTURE.md §1 (Purpose and
scope, Non-goals)

## Goal

Make the repository's documents describe what `jidota` does now, so nobody follows the old
`factory.py` workflow.

## Job to do

| Document | Change |
|---|---|
| `README.md`, Workflow | Done is set by `jidota` when the PR is merged, not by the human |
| `Factory/README.md` | merge delivery, `backlog.md`, local tickets, `next`, `board.json` and the `python -m http.server` dashboard are gone; the spec factory destination comes from the `jidota` configuration, not from `--repo` / `--project`, `published.json` or `~/.claude/spec-factory.json` |
| `Factory/README.md`, Factory section | describes `jidota` and the agents, no longer the `/jidota:code-factory` skill; `skills/code-factory/` is removed |
| `Factory/README.md` and `Graph/README.md` | Python prerequisites, the `scripts/` folders and the copy of `ticket_graph.py` in the plugin are gone; `Graph/PyGraph` stays only as the prototype |
| Memory of the 2026-10-15 design | SQLite, Linear, "one run per repo", "Done always set by a human" and the 90-day retention are superseded |

Add to `Factory/README.md` how to install and start `jidota` (`dotnet tool install`, `jidota init`,
`jidota start`, `jidota status` for the dashboard URL), taken from the commands of ticket 32.

## Automated tests

- `Category=Unit`: no Markdown file of the repository outside `docs/features/` and `tickets/`
  mentions `factory.py`, `board.json`, `backlog.md` or `python -m http.server` (a test scanning the
  files).

## How to verify

Read `README.md` and `Factory/README.md` from the top: every command shown exists in `jidota --help`.

## Acceptance criteria

- [ ] Each row of the table is done
- [ ] No document still describes the Python code factory
- [ ] The install and start commands are documented
