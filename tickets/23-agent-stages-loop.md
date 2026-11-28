# 23 — Build, review, rework and approve stages

**Depends on:** 18, 20, 21, 22
**Reference:** ARCHITECTURE.md §2 (The loop is code), §4 (The job state machine: build, review(n),
rework, approve, blocked), §7.1 (Retry), §7.4 (Within a job), §12 (Invariants 4, 6)

## Goal

Drive a job from `build` to the PR stage, or to a human, by starting the agents and routing on the
first line of their files.

## Job to do

| Stage | Action | Next |
|---|---|---|
| build | builder, mode build | `STATUS: DONE` → review(1); `STATUS: BLOCKED` → blocked, reason `<pass>: <reason>` |
| review(n) | create `round-<n>/`; start every configured reviewer at once; wait for all | rules of ticket 20 |
| rework | resume the builder session (`--resume <builder session id>`), mode rework, with the round folder; if it cannot be resumed, a fresh builder with the same task, and store its session id | review(n+1) |
| approve | approver | `APPROVE` → pr; `ESCALATE` → pr with the reasons on top, then needs-human |

Rules:

1. Commit each transition before starting the next run (Invariant 4).
2. Route only on the first line of the file (Invariant 6), never on the agent's reply.
3. Only reviewers run in parallel; nothing else in a job does (§7.4).
4. Run retries (§7.1):

   | Run end | Behaviour |
   |---|---|
   | `timeout`, `budget` | restarted once; second failure → needs-human |
   | `crashed` | restarted once; second failure → needs-human |
   | `permission_denied` | needs-human with the denied tool and its input |
   | `quota`, `auth` | the job stays at its stage and the run is reported to the pause controller (an interface here; the pause itself is ticket 28) |
   | file missing or malformed | sent back once (ticket 20) |

5. Each restart is a new `agent_runs` row with `attempt` + 1.

## Automated tests

`Category=Integration`, FakeClaude scenario lists + bare git origin + Testcontainers:

- Happy path: build DONE → both reviewers PASS → APPROVE: job reaches `pr`; 4 runs recorded.
- Review `CHANGES` once → rework with `--resume` of the builder session → PASS → approve.
- Rework where `--resume` fails (FakeClaude exits with an error) → fresh builder, new session id
  stored.
- BLOCKED → `blocked` with `<pass>: <reason>`; ESCALATE → pr then needs-human.
- `hang` builder with a short run duration → restarted once → needs-human.
- `permission-denied.jsonl` → needs-human with the tool and input.
- Two reviewers started within the same second (parallel), the approver after both.

## How to verify

`dotnet test --filter FullyQualifiedName~AgentStages`.

## Acceptance criteria

- [ ] Every stage row and run-end row behaves as stated
- [ ] A transition is committed before the next run starts
- [ ] Reviewers run in parallel and the job waits for all of them
- [ ] A rework resumes the builder session, with a fresh builder as fallback
- [ ] No routing reads the agent's reply text
