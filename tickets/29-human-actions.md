# 29 — Human actions: run, approve, rework, cancel

**Depends on:** 08, 09, 10, 19, 20, 24, 26
**Reference:** ARCHITECTURE.md §4 (The job state machine: blocked, needs-human, cancelled; human
rework), §5 (Job event), §6 (Errors), §11 (Caught at validation; Runtime: cancel during a run);
features "Jobs started and released from the dashboard", "Ready tickets picked up from the GitHub
Project"

## Goal

The four actions a human takes on jobs, implemented once in `Jobs/`, so the CLI and the dashboard
share one code path. Each action is recorded with the job: who, when, the note.

## Job to do

| Action | Allowed when | Effect | Refused |
|---|---|---|---|
| run `<ticket \| spec>` | the poller's rules (ticket 26): Ready, dependencies Done, touches, slots; for a spec, each of its tickets meeting them | starts now instead of at the next poll | 422 / exit 2 (`[HUMAN]`), 409 / exit 3 (open job), 422 / exit 4 (not Ready or a dependency not Done, with the list), 409 / exit 5 (busy) |
| approve `<job>` | stage `needs-human` | opens or updates the draft PR (ticket 24); stage `pr` | 409 / exit 3 otherwise, or while a run of the job is active |
| rework `<job> <note>` | stage `needs-human`, `blocked` or `pr` | writes `round-<n>/review-human.md` (n = round + 1, ticket 19), resets the rework count, resumes the builder (a BLOCKED builder restarts at pass 0 with the note as its answer), then a full review round; runs even if the slots are full | 409 / exit 3 otherwise, or while a run is active |
| cancel `<job>` | any open stage | kills the running process tree (run `cancelled`), closes the draft PR if any, removes the worktree (never one with uncommitted changes), keeps the branch, ticket → Todo | 409 / exit 3 for a done or cancelled job |

1. Every action writes a `job_events` row: action, who (the OS user name), when, note.
2. A rework after the PR is open puts the ticket back to In Progress; the next delivery updates the
   same PR (ticket 24).
3. Starting a ticket that is not Ready, or whose dependencies are not Done, is out of scope
   (feature): refuse it.

## Automated tests

`Category=Integration`, FakeClaude + fake hosts + Testcontainers:

- run of a Ready ticket starts it; of a Todo ticket → exit 4; of a ticket with an open job → exit 3.
- approve of a needs-human job opens the PR; of a `build` job → exit 3.
- rework writes the exact `review-human.md`, resets the count, the next round is a full review.
- rework while a run is active → exit 3.
- cancel during a `hang` run: no process left, run `cancelled`, PR closed, worktree removed, branch
  kept, ticket Todo; a dirty worktree is kept and the reason reported.
- Each action leaves one `job_events` row with who, when, note.

## How to verify

`dotnet test --filter FullyQualifiedName~HumanActions`.

## Acceptance criteria

- [ ] Each action behaves as its row states, with the refusal codes of the table
- [ ] Every action is recorded with who, when and the note
- [ ] Cancel never removes a worktree with uncommitted changes
- [ ] A human rework resets the rework count
