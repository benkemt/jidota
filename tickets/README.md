# jidota — implementation tickets

These tickets build the `jidota` .NET tool described in [`../ARCHITECTURE.md`](../ARCHITECTURE.md),
delivering the features of [`../docs/features/code-factory-run-recording.md`](../docs/features/code-factory-run-recording.md).
They are numbered in execution order; each one is self-contained. Every ticket has a **How to
verify** and an **Automated tests** section: the tests run in a pipeline with
`dotnet test jidota.sln --filter Category!=Manual` (the .NET SDK, git and Docker; never a real
`claude`, `gh` or `az` — conventions in ticket 01).

## Order of execution

| # | Ticket | Depends on | Delivers |
|---|---|---|---|
| 01 | [Solution scaffold and test conventions](01-scaffold-solution.md) | — | solution, module folders, test categories, packaged plugin |
| 02 | [Reference `claude -p` runs recorded as fixtures](02-record-reference-claude-runs.md) | 01 | `stream-json` fixtures, answers to the spike questions |
| 03 | [Logging setup and log rules](03-logging-setup.md) | 01 | Serilog JSON files, scopes, levels |
| 04 | [Configuration, data folder and local secrets](04-configuration-and-data-folder.md) | 01 | `config.json`, `<data>/jidota/`, `secrets.json`, `api.token` |
| 05 | [Ticket and spec parsing and validation](05-ticket-and-spec-parsing.md) | 01 | typed tickets and specs, scope work items |
| 06 | [Job naming, touches overlap and remote patterns](06-job-naming-touches-and-remotes.md) | 05 | subject, job id, overlap, host recognition |
| 07 | [Process runner and retry policy](07-process-runner-and-retry.md) | 03 | argv-only processes, tree kill, Polly retry |
| 08 | [Git host](08-git-host.md) | 04, 06, 07 | clone, worktree, push of `factory/<job-id>` only |
| 09 | [GitHub host](09-github-host.md) | 07 | Project, Status, issues, draft PRs |
| 10 | [Azure DevOps host](10-azure-devops-host.md) | 06, 07 | draft PRs, work item links, 4000-char limit |
| 11 | [Database schema, migrations and instance lock](11-database-schema.md) | 04 | EF Core model, migrations, advisory lock |
| 12 | [PostgreSQL container provisioning](12-postgres-container.md) | 04, 07 | container on `127.0.0.1` |
| 13 | [`jidota init`](13-init-command.md) | 04, 09, 11, 12 | prerequisites, config, Status options, database |
| 14 | [Secret masking](14-secret-masking.md) | 04, 07 | masker for every write |
| 15 | [`stream-json` reader and run recorder](15-stream-json-recorder.md) | 02, 11, 14 | runs, tool calls, raw lines, end status |
| 16 | [Fake `claude` executable](16-fake-claude.md) | 02 | FakeClaude for tests |
| 17 | [Generated `--settings` per repository](17-repository-settings-generation.md) | 04, 06 | permissions file per repository |
| 18 | [Agent launcher](18-agent-launcher.md) | 08, 15, 16, 17 | one `claude -p` per run |
| 19 | [Job files and first-line routing](19-job-files.md) | 05, 06 | `spec.md`, `review-human.md`, routing parsers |
| 20 | [Review round rules](20-review-round-rules.md) | 19 | next step after a round |
| 21 | [Status mapping and writer](21-status-mapping-and-writer.md) | 09, 11 | ticket and spec Status |
| 22 | [Job creation stage](22-job-creation-stage.md) | 08, 11, 19, 21 | job, worktree, `spec.md` |
| 23 | [Build, review, rework and approve stages](23-agent-stages-loop.md) | 18, 20, 21, 22 | the agent loop |
| 24 | [Draft PR delivery stage](24-draft-pr-delivery.md) | 09, 10, 14, 23 | push, draft PR, description |
| 25 | [Job result recording](25-job-result-recording.md) | 08, 11, 23, 24 | diff, commits, tests, outcome, work items |
| 26 | [Scheduler](26-scheduler.md) | 05, 06, 11, 21, 22 | eligibility, slots, touches |
| 27 | [Poller](27-poller.md) | 09, 10, 21, 25, 26 | poll, PR states, Status restore |
| 28 | [Global pause on quota and auth](28-quota-and-auth-pause.md) | 15, 23 | pause, resume at `resetsAt` |
| 29 | [Human actions](29-human-actions.md) | 08, 09, 10, 19, 20, 24, 26 | run, approve, rework, cancel |
| 30 | [Recovery, drain stop, single instance](30-recovery-and-drain-stop.md) | 11, 21, 23, 28 | restart safety |
| 31 | [Local API and its token](31-local-api.md) | 04, 28, 29, 30 | routes on `127.0.0.1` |
| 32 | [CLI commands](32-cli-commands.md) | 13, 30, 31 | start, stop, status, resume, actions, clean |
| 33 | [Dashboard: Jobs view](33-dashboard-jobs-view.md) | 25, 31 | live job cards and actions |
| 34 | [Dashboard: Spending view](34-dashboard-spending-view.md) | 25, 33 | cost per work item |
| 35 | [Dashboard: Run replay and comparison](35-dashboard-run-view.md) | 15, 33 | step-by-step runs |
| 36 | [Port `fetch_source.py`](36-port-spec-fetch.md) | 07, 09 | `jidota spec fetch` |
| 37 | [Port `ticket_graph.py`](37-port-spec-graph.md) | 05 | `jidota spec graph` |
| 38 | [Port `publish_github.py`](38-port-spec-publish.md) | 04, 05, 09 | `jidota spec publish` from the config |
| 39 | [Port `branch_to_pr.py`](39-port-branch-to-pr.md) | 05, 06, 07, 09, 10, 11 | `jidota pr collect \| open` |
| 40 | [Port `workitems.py target \| check`](40-port-workitems-target-and-check.md) | 06, 07, 10 | `jidota workitems target \| check` |
| 41 | [Port `workitems.py create`](41-port-workitems-create.md) | 40 | `jidota workitems create` |
| 42 | [Skills call `jidota`; Python removed](42-switch-skills-to-jidota.md) | 36–41 | plugin without Python or code-factory skill |
| 43 | [Align the documentation](43-align-documentation.md) | 32, 33, 42 | READMEs |
| 44 | [Invariant and edge-case suite](44-invariants-and-edge-cases-suite.md) | 01–43 | pipeline suite |

## Parallel tracks

Ticket 01 is the only strictly serial step. After it, these tracks progress in parallel:

- **foundations** 03, 04, 05 → 06, then 07 → hosts 08, 09, 10, 12; 11 after 04
- **agents** 02 → 16; 14 → 15; 17 → converge at 18
- **job files** 19 → 20
- **ports** 36, 37, 38, 39, 40 → 41 → 42 (needs only the hosts, not the job loop)

They converge at 21–23 (the job loop), then 24 → 25 → 26 → 27, with 28 → 29 → 30 → 31 → 32 and the
dashboard 33 → 34, 35. 43 and 44 close the backlog.

## Coverage map

| ARCHITECTURE.md / features | Covered by |
|---|---|
| §1 Purpose and scope, guarantees | 15, 21, 23, 24, 30 |
| §1 Non-goals | 10, 24, 25, 26, 27, 29, 33, 42 (each carried as a constraint) |
| §2 Design principles | 07, 18, 19, 21, 23, 26 |
| §2.1 Architecture style | 01 (tree and rules), every ticket's location |
| §2.2 Cross-cutting libraries | 01, 03, 04, 05, 07, 11, 16, 31, 33, 34, 35 (bUnit) |
| §3 Boundaries, trust boundaries | 05, 08, 09, 10, 12, 17, 18, 19, 31, 36–41 |
| §4 Components | 01, 03–19, 21, 26, 27, 31, 36–41 |
| §4 The job state machine | 20, 22, 23, 24, 29 |
| §4 One agent run | 17, 18 |
| §4 Privilege rules | 08, 11, 15, 17, 21 |
| §5 Data entities, run fields, job id | 04, 06, 08, 11, 15, 19, 21, 22, 25 |
| §5 Schema, integrity | 11, 15, 21 |
| §6 Commands | 13, 32, 36–41 |
| §6 Local API | 31 |
| §6 Errors, compatibility | 29, 31, 32, 36–41 |
| §7.1 Retry | 07, 15, 20, 23, 24, 27, 28 |
| §7.2 Rollback | 21, 22, 24, 29 |
| §7.3 Recovery | 30 |
| §7.4 Concurrency | 06, 08, 11, 22, 23, 26, 30 |
| §8.1 Latency | 27 |
| §8.2 Throughput | 26, 28 |
| §8.3 Limits (incl. Not decided: port, image, log retention, quota threshold) | 03, 04, 07, 10, 11, 12, 18, 20, 26, 27, 28, 31 |
| §9.1 Identity (incl. Not decided: command source, sandbox) | 04, 12, 13, 17, 31, 32 |
| §9.2 Input | 05, 06, 07, 09, 10, 18, 19, 33, 35, 41 |
| §9.3 Secrets | 04, 12, 14, 24 |
| §10 Observability, §10.1 Logs, §10.2 Tracing | 03, 32, 33, 35 |
| §11 Edge cases — caught at validation | 05, 26, 29, 44 |
| §11 Edge cases — caught before the side effect | 22, 26, 27, 44 |
| §11 Edge cases — runtime | 10, 20, 22, 23, 24, 27, 28, 29, 30, 44 |
| §11 Traps already met | 02, 05, 08, 09, 13, 17, 18, 22, 26 |
| §11 To verify in the first spike | 02 (resetsAt, resume cost), 13 (Status mutation), 32 (Linux detach) |
| §12 Invariants 1–13 | 44 (one test each); enforced in 08, 11, 14, 17, 18, 19, 21, 26, 36–41 |
| Feature: runs unattended, every run recorded | 15, 18, 23, 44 |
| Feature: every implemented ticket keeps its result | 24, 25 |
| Feature: cost and time per work item (Jobs, Spending, Run views, comparisons) | 33, 34, 35 |
| Feature: jobs started and released from the dashboard | 29, 33 |
| Feature: Ready tickets picked up from the Project, Status, spec Status | 21, 26, 27 |
| Feature: one command (init, start, stop, status, resume, actions, clean, ports, no Python) | 13, 30, 32, 36–42 |
| Features: documents to align | 43 |
