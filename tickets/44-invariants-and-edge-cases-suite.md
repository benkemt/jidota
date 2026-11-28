# 44 — Invariant and edge-case test suite

**Depends on:** 01–43
**Reference:** ARCHITECTURE.md §11 (Edge cases), §12 (Invariants); features, Success Criteria of each
feature

## Goal

One end-to-end suite that runs in the pipeline and pins every invariant and every edge case, so a
change that breaks one fails the build.

## Job to do

Test bed, all in `Category=Integration`: Testcontainers PostgreSQL, a bare git `origin` per test
repository, FakeClaude (ticket 16) with scenario lists, fake GitHub and Azure DevOps hosts holding
an in-memory Project, issues and PRs, an injected clock. Run `serve` in-process.

**One test per invariant** (§12):

| # | Test |
|---|---|
| 1 | Status writes for a job: only `jidota` writes them while open; Done only after the fake PR is merged |
| 2 | After every scenario, the bare origin has no new branch other than `factory/<job-id>`, no forced update; every PR created is a draft |
| 3 | FakeClaude checks at start that its `agent_runs` row exists with status `running` |
| 4 | Kill the host between a transition commit and the next run: the stored stage is the committed one |
| 5 | No recorded argv task contains a line of the ticket or spec body |
| 6 | A builder whose reply says "DONE" but whose `build.md` says `STATUS: BLOCKED` goes to blocked |
| 7 | A secret injected in a fixture is `***` in `run_lines` and `tool_calls` |
| 8 | 10 Ready tickets with overlapping touches in one repository: never two open at once; never more than 3 running |
| 9 | Every process started has its working directory under `<data>/jidota/` (FakeClaude and the fake git wrapper record it) |
| 10 | Cancel and clean on a dirty worktree keep it |
| 11 | Scan the database, the log files, the PR bodies and the dashboard HTML for the injected secrets: none found |
| 12 | Parity golden files of tickets 36–41 all pass |
| 13 | Every recorded argv of a run holds `--permission-prompts none`, `--setting-sources user`, `--strict-mcp-config`, and never `--dangerously-skip-permissions` |

**Edge cases** (§11): one test per row of "Caught at validation", "Caught before the side effect"
and "Runtime", asserting the behaviour column; most already exist in tickets 22–32 — reference them
from a single list test so a missing one fails.

**Feature success criteria**: a Ready ticket with dependencies Done is picked up within one poll;
the Status follows its job until Done for tickets of two repositories in one Project; every job has
a record of each run, finished or not; stored totals equal `result`; `jidota stop` never interrupts
a run; a job can be started, cancelled and released through the API.

## Automated tests

This ticket is the tests: `dotnet test jidota.slnx --filter Category!=Manual` in the pipeline, with
Docker available.

## How to verify

The pipeline run is green; deliberately breaking one invariant (for example adding `--force` to
the push) makes its test fail.

## Acceptance criteria

- [ ] Each of the 13 invariants has a named test
- [ ] Each edge-case row of §11 has a test asserting its behaviour
- [ ] Each feature success criterion has a test
- [ ] The suite runs in a pipeline with only the .NET SDK, git and Docker
