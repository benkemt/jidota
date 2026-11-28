# 25 — Job result recording

**Depends on:** 08, 11, 23, 24
**Reference:** ARCHITECTURE.md §5 (Job result, Work item); feature "Every implemented ticket keeps
its result"

## Goal

Store with each job what it produced and how it ended, linked to its ticket, its spec and the work
items it implements.

## Job to do

| What | Source | When |
|---|---|---|
| Diff and diff stat | `git diff origin/<start_branch>...factory/<job-id>` (ticket 08) | at each delivery |
| Commits of the job branch | `git log origin/<start_branch>..factory/<job-id>` | at each delivery |
| Test counts (passed, failed, skipped; Before and After) | the `## Test counts` table of `build.md`, and of each `## Round <n>` | after each build or rework |
| Review rounds | each reviewer's verdict, number of rework rounds | after each round (ticket 20) |
| Approver decision | first line and first reason of `decision.md` | after approve |
| Outcome and reason | done, needs-human, blocked, cancelled | at each final transition |
| PR state and merge commit | host PR state; `mergeCommit` (GitHub) or `lastMergeCommit` (ADO) | when the PR is merged |
| Work item links | every `(scope)` line of the spec's `sources` (ticket 05): ADO work item, or GitHub issue when the spec came from one | at job creation |

Only the reference and title of a work item are stored; its contents are never read (§1 non-goal).
Masked before storage (ticket 14).

## Automated tests

- `Category=Unit`: test counts parsed from a `build.md` with a build section and two rounds.
- `Category=Unit`: a `build.md` with no Test counts table gives no counts, no error.
- `Category=Integration` (Testcontainers, bare git): after delivery, the job row holds the diff
  and the commits of the branch.
- `Category=Integration`: a spec with two ADO scope items and one context item gives two
  `job_work_items` rows.
- `Category=Integration`: merged PR on the fake host stores the merge commit.

## How to verify

Run the end-to-end happy path of ticket 23 then query the job: every row of the table has a value.

## Acceptance criteria

- [ ] Every row of the table is stored for a finished job, whatever its outcome
- [ ] Each job is linked to every `(scope)` work item, and none of the `(context)` ones
- [ ] No work item content is read
- [ ] Missing optional parts (no test counts, no PR) are stored as absent, not as errors
