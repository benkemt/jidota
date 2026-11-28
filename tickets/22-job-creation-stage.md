# 22 — Job creation stage

**Depends on:** 08, 11, 19, 21
**Reference:** ARCHITECTURE.md §4 (The job state machine: created), §5 (Clone, Worktree, Job folder,
job id), §7.2 (Rollback), §7.4 (Git), §11 (Caught before the side effect, Runtime)

## Goal

Turn an eligible ticket into a job: clone or fetch its repository, create its worktree and branch,
write `spec.md`, record the job, and set the ticket to In Progress.

## Job to do

1. Clone the `code_repo` on the first job of a repository, otherwise fetch (ticket 08).
2. Check `origin/<start_branch>` exists.
3. Take the next job id from the global sequence (ticket 11), build the branch `factory/<job-id>`.
4. In the transaction given by the caller (the scheduler of ticket 26 calls this step while it holds
   its lock): `git worktree add --no-checkout`, insert the job at stage `created`, its job event,
   its Status to write (In Progress). Tests call this step directly.
5. Outside the lock: fill the worktree (`git reset --hard -q`), write `spec.md` (ticket 19) in the
   job folder, then move to `build`.

| Case | Behaviour |
|---|---|
| `code_repo` cannot be cloned (no access, unknown host) | Ticket → Needs human with the cause; no job branch |
| `start_branch` missing on `origin` | Ticket → Needs human |
| The worktree folder already exists and no job owns it | No job created, nothing written in that folder; ticket → Needs human, reason `worktree <path> already exists` (Needs human rather than a plain error: the poller would retry it at every poll). A human removes the folder and sets the ticket to Ready again |
| Filling the worktree fails | Job and branch exist: job → needs-human, reason `checkout of the worktree failed: <git message>`; no agent runs. The human fixes the cause, cancels the job, sets the ticket to Ready again |

Constraints: the worktree is created from `origin/<start_branch>` after the fetch, never from a
local branch, and only under `<data>/jidota/` (Invariant 9). No checkout under the lock (trap §11).
A job resumed after a restart reuses the worktree recorded for it; a folder no job owns is never
reused (§7.2).

## Automated tests

`Category=Integration`, bare git origin + Testcontainers + fake GitHub host:

- Happy path: job row at `build`, worktree on `factory/<job-id>` at `origin/main`, `spec.md` written,
  Status In Progress written.
- Unknown host `code_repo` → ticket Needs human, no job row.
- Missing `start_branch` → Needs human, no job row.
- Pre-existing worktree folder → no job row, folder untouched, Needs human with the path.
- Fill failure (read-only folder, Linux) → job at needs-human with the git message, no run started.

## How to verify

`dotnet test --filter FullyQualifiedName~JobCreation`.

## Acceptance criteria

- [ ] Each row of the table behaves as stated, with its reason text
- [ ] The worktree starts at `origin/<start_branch>` after a fetch
- [ ] Job, event and Status to write commit together
- [ ] No checkout happens under the scheduler lock
- [ ] No folder outside `<data>/jidota/` is written
