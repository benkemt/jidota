# 21 — Ticket and spec Status mapping and writer

**Depends on:** 09, 11
**Reference:** ARCHITECTURE.md §2 (The Project is the queue), §4 (The job state machine), §5
(Integrity), §7.1 (Status write), §12 (Invariant 1); feature "Ready tickets picked up from the
GitHub Project"

## Goal

One place that says which Status a ticket and its spec must have for a job, and that writes it to
the Project after the database commit.

## Job to do

1. **Ticket Status from the job stage**:

   | Job | Ticket Status |
   |---|---|
   | created, build, review, rework, approve (including a rework after the PR is open) | In Progress |
   | pr (draft PR open or updated) | In Review |
   | blocked, needs-human (escalated, out of rework rounds, PR closed without merge, clone or push failed) | Needs human |
   | cancelled | Todo |
   | done (PR merged) | Done |

2. **Spec Status** derived from its tickets: In Progress when the first of its tickets starts; Done
   when all its tickets are Done (`[HUMAN]` tickets included). `jidota` never sets a spec to Ready.
3. **Write after commit**: the transition commits stage, event and the Status to write in one
   transaction (ticket 11); the GitHub write happens after the commit. A failed write (after the
   retries of ticket 07) is redone at the next poll — store "Status pending" on the job.
4. **Done only when the PR is merged** (Invariant 1). While a job is open, only `jidota` writes the
   ticket's Status.
5. Status options are found by name in the field list (ticket 09); a missing option (In Review,
   Needs human) is an error that says to run `jidota init`.

## Automated tests

- `Category=Unit`: each row of the table; the spec rules with 3 tickets (none started, one started,
  all Done, one `[HUMAN]` not Done).
- `Category=Integration` (Testcontainers, fake GitHub host): a failing Status write leaves "Status
  pending"; the next poll call writes it and clears the flag.
- `Category=Unit`: no code path maps a stage other than done to Done.

## How to verify

`dotnet test --filter FullyQualifiedName~StatusMapping`.

## Acceptance criteria

- [ ] Every stage maps to the Status of the table
- [ ] A spec is In Progress at its first started ticket and Done only when all are Done
- [ ] The Status is written after the database commit, and retried at the next poll on failure
- [ ] Done is written only for a merged PR
- [ ] A missing Status option fails with a message naming `jidota init`
