# 26 — Scheduler: eligibility, slots and touches

**Depends on:** 05, 06, 11, 21, 22
**Reference:** ARCHITECTURE.md §2 (The Project is the queue), §7.4 (Concurrency), §8.2 (Throughput),
§11 (Caught at validation, Caught before the side effect), §12 (Invariant 8); feature "Ready tickets
picked up from the GitHub Project"

## Goal

Decide which tickets start now, whether the request comes from the poller, the CLI or the
dashboard, under one lock, so no ticket is started twice and the limits always hold.

## Job to do

1. **Eligible** when, at the time of the decision:
   - the issue is open, its Status is Ready, it is a ticket (not a spec), not `[HUMAN]`;
   - it has no open job;
   - every `depends_on` ticket has Status Done (`[HUMAN]` dependencies too): the Status is the only
     source of truth for dependencies, not the commit subject (a host rewrites the squash message
     of a merged PR — trap of §11).
2. **Not eligible, no job**:

   | Case | Behaviour |
   |---|---|
   | invalid yaml / no `id` | ticket → Needs human, `invalid ticket yaml` |
   | unknown dependency | ticket → Needs human with the unknown id |
   | `[HUMAN]` ticket at Ready | ignored, `Warning` log |
   | spec issue (`child_specs`) | never started |
   | closed issue at Ready | ignored |
   | a dependency not Done | waits; reported with the dependencies |

3. **Busy** (stays Ready, started at a later poll): running jobs (stages created, build, review,
   rework, approve) at the parallel-jobs limit (3, across all repositories); or `touches` overlap an
   open job (not done or cancelled) **of the same repository** (ticket 06); a ticket with no
   `touches` runs alone in its repository. Jobs at pr, needs-human, blocked take no slot but still
   hold their files.
4. **Serialized**: eligibility, slot and touches checks and the creation of the job (ticket 22)
   happen under one in-process lock and one transaction (§7.4).
5. Ordering among eligible tickets is not specified by the architecture: use the Project item
   order, and record that choice in a comment.

## Automated tests

`Category=Unit` with an in-memory Project and board:

- Each row of table 2, with its outcome.
- Dependencies: one Done and one In Review → waits; both Done → eligible.
- Slots: 3 running in two repositories → busy; one at `pr` frees a slot.
- Touches: same path in the same repository → busy; same path in another repository → eligible;
  no touches → alone in its repository only.
- `Category=Integration`: 20 concurrent start requests for the same ticket create one job.

## How to verify

`dotnet test --filter FullyQualifiedName~Scheduler`.

## Acceptance criteria

- [ ] A ticket starts only when Ready, open, not `[HUMAN]`, with all dependencies Done
- [ ] Running jobs never exceed the limit; overlapping touches never run in one repository (Invariant 8)
- [ ] Concurrent requests never start a ticket twice
- [ ] Each ineligible case behaves as in the table
