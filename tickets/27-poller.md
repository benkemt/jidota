# 27 — Poller

**Depends on:** 09, 10, 21, 25, 26
**Reference:** ARCHITECTURE.md §4 (Poller/), §7.1 (poll skipped, Status write redone), §8.1, §8.3
(Poll interval), §11 (Caught before the side effect, Runtime: PR closed, PR merged)

## Goal

Every poll interval, read the Project, hand eligible tickets to the scheduler, follow open PRs, and
put back any Status changed by hand.

## Job to do

Every 5 minutes (`config.json`), as a hosted service:

1. Read the Project items with their Status and issue bodies (ticket 09).
2. Give the items to the scheduler (ticket 26).
3. For each job at `pr`, read the PR state on its host (tickets 09, 10):

   | PR state | Behaviour |
   |---|---|
   | OPEN | nothing |
   | MERGED | job → done (Status Done); merge commit stored (ticket 25); spec Done when all its tickets are Done; dependents eligible from the next poll |
   | CLOSED (not merged) | job → needs-human, reason `PR closed without merge` |

4. **Restore**: a ticket with an open job whose Status differs from the job's Status (ticket 21) is
   put back, with a `Warning` log. A ticket set to Ready while its job is open is put back too. Only
   `cancel` stops a job.
5. Redo the Status writes left pending (ticket 21).
6. A poll that fails after retries is skipped; the next one catches up. Log `Information` at the end
   of each poll: tickets seen, jobs started.
7. Not a conflict detector: a PR in conflict with its start branch is not detected (§1 non-goal).

## Automated tests

`Category=Integration`, fake hosts + Testcontainers, clock injected:

- Two polls 5 minutes apart: a ticket set to Ready between them starts at the second.
- PR MERGED → job done, Status Done, spec Done when it was the last ticket.
- PR CLOSED → needs-human with the reason.
- Status changed by hand to Todo on a running job → put back to In Progress, `Warning` logged.
- The Project read fails 3 times → poll skipped, no state change, next poll works.

## How to verify

Start `serve` against a test Project, set a ticket to Ready, and watch the dashboard within 5
minutes.

## Acceptance criteria

- [ ] A Ready eligible ticket starts within one poll interval when a slot is free
- [ ] Each PR state row behaves as stated
- [ ] A Status changed by hand on an open job is put back at the next poll
- [ ] A failed poll changes nothing and the next poll recovers
