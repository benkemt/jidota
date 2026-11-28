# 11 — Database schema, migrations and the instance lock

**Depends on:** 04
**Reference:** ARCHITECTURE.md §2.2 (Data access), §5 (Data, Schema, Integrity), §7.4 (One instance
per machine), §12 (Invariants 3, 4)

## Goal

The EF Core model of everything `jidota` owns, its migrations, and the PostgreSQL advisory lock
that keeps one instance per machine.

## Job to do

EF Core with `Npgsql.EntityFrameworkCore.PostgreSQL`, entities in `Data/`, migrations in
`Data/Migrations/`. `Data/` holds the only `DbContext` (§2.1).

| Table | Holds | Lifecycle |
|---|---|---|
| `jobs` | id (`<seq>-<ticket id>-<slug>`), ticket URL, ticket id, key, spec URL and title, code repository, start branch, branch, worktree, touches, stage, round, reason, builder session id, diff, commits, test counts, outcome | one per started ticket; stage updated at each transition; never deleted |
| `job_events` | job, time, kind (transition or human action), from and to stage, who, note | append-only |
| `review_rounds` | job, round number, each reviewer's verdict (`pending`, `PASS`, `CHANGES`, `INVALID`), human round or not | one per round |
| `agent_runs` | job, agent, round, session id, model, input / output / cache-creation / cache-read tokens, `total_cost_usd`, `num_turns`, `duration_ms`, `duration_api_ms`, starting commit (repository, HEAD, clean or dirty), attempt, end status | row created before the process starts (`running`) |
| `tool_calls` | run, order, tool name, input, result, success or failure, start and end time | one per `tool_use` / `tool_result` pair |
| `run_lines` | run, order, masked raw line | every line, kept with no time limit |
| `pull_requests` | job, host, number, URL, state, merge commit | one per job PR |
| `job_work_items` | job, tracker (ADO or GitHub), id, title | one per `(scope)` item |

End statuses of a run: `running`, `finished`, `timeout`, `budget`, `crashed`, `cancelled`, `quota`,
`auth`, `permission_denied`. A job-id sequence across all repositories.

1. A transition is one transaction: stage, job event and the Status to write are committed together
   (§5 Integrity). Provide the unit-of-work method later tickets use.
2. On start of `serve`, the instance refuses to run on a database behind its migrations (§5).
3. Advisory lock: `pg_try_advisory_lock(<constant key>)` taken at start of `serve`; not acquired →
   refuse to start with "another jidota instance is running" (§7.4).

## Automated tests

`Category=Integration`, Testcontainers PostgreSQL:

- Migrations apply on an empty database; a second apply is a no-op.
- A database with a pending migration makes the start check fail.
- Two connections: the second `pg_try_advisory_lock` fails while the first holds it.
- A transition saved with a simulated failure after the job event leaves neither the stage nor the
  event written.
- `job_events` rows are never updated or deleted by the data API (no such method).

## How to verify

`dotnet test --filter "Category=Integration&FullyQualifiedName~Data"` with Docker running.

## Acceptance criteria

- [ ] Every table and field of the list exists after `jidota init` applies the migrations
- [ ] Stage, job event and Status to write commit in one transaction
- [ ] The instance refuses to start behind its migrations
- [ ] A second instance cannot take the advisory lock
- [ ] No API deletes a job or updates a job event
