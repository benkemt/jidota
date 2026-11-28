# 24 — Draft PR delivery stage

**Depends on:** 09, 10, 14, 23
**Reference:** ARCHITECTURE.md §1 (guarantees, non-goals), §4 (The job state machine: pr), §7.1
(push or PR creation), §7.2 (Rollback), §8.3 (ADO PR description), §12 (Invariants 2, 11); feature
"Every implemented ticket keeps its result"

## Goal

Deliver an approved or escalated job as a draft pull request into its start branch, on GitHub or
Azure DevOps, with a description built from the job files.

## Job to do

1. Refuse when the worktree has uncommitted changes (`the worktree <path> has uncommitted changes,
   PR refused`).
2. Push `factory/<job-id>` (ticket 08). Never the start branch, never with force (Invariant 2).
3. Find the open PR of the branch; update it if found, otherwise create a **draft** PR into
   `start_branch`, title = commit subject. Idempotent on re-run (§7.2).
4. **Description**, as `pr_body` of `factory.py`, masked (ticket 14) before it is sent:
   - escalated: `> **Escalated: a human decides.** <reason>` on top;
   - `- Ticket: <id> — <ticket URL>`, `- Spec: <title> — <spec URL>`, `- Job: <id>, <branch> → <start_branch>`;
     **no bare key**: `#41` would link to an issue or work item of the code repository;
   - `## Proof — Round <n>` from the last `## Round` section of `build.md`, else `## Proof` and
     `## Test counts`;
   - `## Reviews`: a table round × reviewer verdicts;
   - `## Decision: <first line of decision.md>` and its reasons;
   - on a GitHub host, the `(scope)` work items named (features);
   - footer: drafted by the JidoTa code factory, job files in the jidota folder, marking ready,
     approving and completing stay human.
5. Azure DevOps host: link the `(scope)` work items (`az repos pr work-item add`); truncate the
   description to 4000 characters with the pointer (ticket 10).
6. Store the PR (ticket 11); stage `pr` (Status In Review), or stay `needs-human` when escalated.
7. Push or PR failure after retries → needs-human, reason `draft PR failed: <message>`.

Non-goals: never mark ready, approve, merge, or push a start branch.

## Automated tests

- `Category=Unit`: description golden files for a GitHub and an ADO job, escalated and not.
- `Category=Unit`: no line of the description holds a bare `#<n>`.
- `Category=Integration` (bare git origin, fake hosts): push creates only `factory/<job-id>`; a
  second delivery updates the PR instead of creating one.
- `Category=Unit`: ADO host links the scope work item ids; GitHub host names them in the body.
- `Category=Unit`: failed push → needs-human with `draft PR failed:`.
- `Category=Unit`: a secret in `build.md` is `***` in the description.

## How to verify

`dotnet test --filter FullyQualifiedName~PrDelivery`.

## Acceptance criteria

- [ ] Only `factory/<job-id>` is pushed, never with force
- [ ] The PR is always a draft; a re-run updates it
- [ ] The description has every part above, masked, with no bare key
- [ ] ADO: work items linked, description ≤ 4000 characters
- [ ] Escalated jobs get the PR and stay needs-human
