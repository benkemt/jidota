# 20 — Review round rules

**Depends on:** 19
**Reference:** ARCHITECTURE.md §4 (The job state machine: review(n), human rework), §7.1 (Agent file
missing or first line malformed), §8.3 (Max rework rounds, Reviewers)

## Goal

Decide, from the files of a finished round, what a job does next: wait, send a reviewer back,
approve, rework, or go to a human. A pure function, ported from `round_cmd` of `factory.py`.

## Job to do

Input: the round number `n`, the configured reviewers, the max rework rounds (2), the verdicts of
earlier rounds, and the files of `round-<n>/`.

1. **Expected files**: `review-human.md` alone when it exists (a human round), otherwise
   `review-<name>.md` for each reviewer of the configuration (`security`, `code`).
2. **Verdict per file**: missing → `pending`; first line `VERDICT: PASS` / `VERDICT: CHANGES`
   (ticket 19); anything else → `INVALID`.
3. **Rework rounds spent**: walk the earlier rounds backwards, stop at the last human round, count
   the rounds holding a `CHANGES`. A human rework resets the count.
4. **Next**, in this order:

   | Condition | Next |
   |---|---|
   | a file is missing | `wait` (the reviewer that returned without its file is sent back once) |
   | a file is malformed | `resend` (sent back once) |
   | no `CHANGES` | `approve` |
   | `CHANGES` and (human round or spent < max) | `rework` |
   | otherwise | `needs-human`, reason `still CHANGES after <max> rework rounds` |

5. **Sent back once**: an agent sent back for a missing or malformed file that fails again sends the
   job to needs-human with the reason `<agent>: malformed <file>` (or `missing <file>`). Same rule
   for `build.md` and `decision.md`.
6. Store each round's verdicts in `review_rounds` (ticket 11).

## Automated tests

`Category=Unit`, table-driven:

- Round 1, both `PASS` → `approve`; one `CHANGES` → `rework`.
- Round 3 after two `CHANGES` rounds → `needs-human` with the reason above.
- Round 3 after a human round 2 → `rework` (count reset).
- Human round with `CHANGES` → `rework` whatever the count.
- One file missing → `wait`; one `INVALID` → `resend`; same failure on the second try →
  needs-human with `<agent>: malformed <file>`.

## How to verify

`dotnet test --filter FullyQualifiedName~RoundRules`.

## Acceptance criteria

- [ ] Each row of the table is covered by a test with that exact outcome
- [ ] A human round expects only `review-human.md` and resets the rework count
- [ ] An agent is sent back once at most for the same file
- [ ] The reason texts are the ones above
