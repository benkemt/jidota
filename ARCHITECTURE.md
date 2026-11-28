# Architecture — jidota

How the `jidota` .NET tool is built: the code factory orchestrator that runs every agent as its own
`claude -p` process, records every run in PostgreSQL, picks up Ready tickets from the GitHub
Project, and serves a local dashboard. For the engineer or agent who implements or changes it. The
features it delivers are in [`docs/features/code-factory-run-recording.md`](docs/features/code-factory-run-recording.md).

**Contents**

1. [Purpose and scope](#1-purpose-and-scope)
2. [Design principles](#2-design-principles) — [style](#21-architecture-style) · [libraries](#22-cross-cutting-libraries)
3. [Boundaries](#3-boundaries)
4. [Components](#4-components)
5. [Data](#5-data)
6. [API contract](#6-api-contract)
7. [Failure and recovery](#7-failure-and-recovery)
8. [Performance and limits](#8-performance-and-limits)
9. [Security](#9-security)
10. [Observability](#10-observability)
11. [Edge cases](#11-edge-cases)
12. [Invariants](#12-invariants)

---

## 1. Purpose and scope

`jidota` is one .NET tool that holds the whole of JidoTa on the owner's machine. It replaces
`factory.py` and the `/jidota:code-factory` skill. It polls the GitHub Project that holds the
specs and tickets and starts a job for each Ready ticket in the code repository the ticket names.
It drives each job through build, review, rework and approval by starting the plugin's agents as
separate `claude -p` processes, and delivers every job as a draft pull request. It records every
agent run, every job result and the link to the work items, and shows them on a local dashboard.
It also carries, as subcommands, the scripts of the interactive skills (spec factory,
branch-to-pr, workitems), so no Python is needed.

It guarantees:

- every agent run has a record, finished or not, with its tokens, cost, turns, durations, tool
  calls, starting commit and masked raw output;
- every job is delivered as a draft PR; nothing else is ever pushed;
- the Status of a ticket with an open job follows that job, and is written by `jidota` only;
- a job survives a stop, a crash or a reboot: it carries on at its next step on the next start;
- the routing of a job never depends on what a model answers, only on the first line of the file
  the agent wrote.

### Non-goals

The component deliberately does not:

- **Run the spec factory unattended** — spec-writer and ticket-writer stay interactive skills; their
  runs are not recorded. `jidota` only provides their scripts as subcommands.
- **Merge, approve or mark a PR ready, or push a start branch** — a human merges every PR. The local
  squash-merge of `factory.py` is gone.
- **Run local or unpublished tickets** — `specs/<slug>/tickets/T<n>.md`, `factory/backlog.md` and
  `next` are gone. A ticket must be an issue in the Project.
- **Read the contents of an ADO work item** — only the reference from the spec's `sources` is kept;
  nothing is read from or written to the work item, except the PR link on an Azure DevOps host.
- **Comment on the ticket's issue** — results, cost and time are on the dashboard.
- **Serve more than one user, or run on more than one machine per Project** — the dashboard listens
  on localhost; two `jidota` instances polling one Project would both start the same tickets, and
  nothing guards against it.
- **Run specs that span several code repositories** — a spec has one `code_repo`.
- **Detect a PR that conflicts with its start branch** — the host shows it; a human asks for a rework.
- **Pick tickets by assignee or label.**

---

## 2. Design principles

**The loop is code, the agents are models.** The `SKILL.md` of the code factory was a program
written for an LLM orchestrator. It becomes a state machine in C#: "two rework rounds, then
needs-human" is an `if`, not an instruction a model may apply differently from one run to the next.
Only builder, reviewers and approver are LLM runs. Passing the skill to a single `claude -p` was
rejected: one session for all agents gives one `total_cost_usd` for all of them, a session of
several hours that takes every job down when it dies, and a context that grows with every job.

**One agent run, one process, one record.** Each agent starts as its own `claude -p`, with a
session id chosen by `jidota` before the process starts. That is what gives cost and tokens per
agent, a timeout and a budget per run, a cancel that kills one process tree, and a rework that
resumes exactly one session.

**Files are the interface with agents, the database is the memory of the loop.** Agents read and
write the same job files as today (`spec.md`, `build.md`, `round-<n>/review-<name>.md`,
`decision.md`); prompts carry paths only, never ticket text. Every transition of a job is written
to PostgreSQL before the next run starts, so a restart finds each job where it stopped.

**External tools through their CLIs, behind an interface.** `git`, `gh`, `az`, `docker` and `claude`
are run as processes, with the user's own sessions: `jidota` stores no GitHub or Azure DevOps
token. Each sits behind an interface so the whole loop can run in tests against a fake `claude`
that replays recorded output.

**The Project is the queue and `jidota` owns the Status of running work.** A human sets Ready; from
then on, `jidota` writes the Status until the job ends, and puts it back if someone changes it by
hand. This keeps one source of truth for dependencies: a dependency is done when its Status is Done.

### 2.1 Architecture style

**Modular monolith with adapters**, applied at **the `jidota` tool as a whole**: one project, one
process, one module per folder under `src/Jidota/`.

A module uses another module only through its public types; the external tools are reached only
through the interfaces of `Hosts/` and `Agents/`. No module other than `Hosts/` and `Agents/`
starts a process, and no module other than `Data/` holds a `DbContext`.

```
jidota/
  ARCHITECTURE.md
  jidota.sln
  src/Jidota/
    Cli/          commands (System.CommandLine)
    Web/          local API and Blazor Server dashboard
    Poller/       GitHub Project -> eligible tickets, PR state
    Jobs/         job state machine, scheduler (slots, touches)
    Agents/       claude -p launch, stream-json reading, settings generation
    Recording/    runs, tool calls, masking
    Hosts/        git, GitHub (gh), Azure DevOps (az), docker
    Spec/         spec fetch | graph | publish (ported spec factory scripts)
    BranchToPr/   pr collect | open (ported branch_to_pr.py)
    WorkItems/    workitems target | check | create (ported workitems.py)
    Data/         EF Core context, entities, migrations
  tests/Jidota.Tests/
  Factory/        the Claude Code plugin (agents, skills), packaged with the tool
  Graph/          ticket graph prototype (GraphNet is the base of Spec/ graph)
```

**Rejected:** vertical slice per use case (StartJob, Approve, Rework, Poll…) — every use case
acts on the same job state machine, which would end up in a shared folder anyway; the modules
above follow the parts of the system that change for different reasons.

**Enforced by:** nothing automated; review of every PR.

### 2.2 Cross-cutting libraries

The target framework is `net10.0`, the one `Graph/GraphNet` already uses, on Windows and Linux.
Code that differs by OS (secret storage, detaching the instance) checks `OperatingSystem.IsWindows()`
in one place, in `Cli/` or `Data/`, never scattered. No version below is
pinned except the one read from a manifest.

| Concern | Choice | Why | Configured in |
|---|---|---|---|
| Command line | `System.CommandLine` | One parser for `jidota` and all its subcommands | `Cli/` |
| Host, DI | `Microsoft.Extensions.Hosting`, built-in DI | Poller and job loop are hosted services in the same host as the web app | `Program.cs` |
| Local API, dashboard | ASP.NET Core minimal API + Blazor Server | All C#; live updates over SignalR without writing JS; one circuit per tab is fine for one user | `Web/` |
| Configuration | `System.Text.Json` into typed options | One `config.json`, written by `jidota init`, read by every command | `Cli/Init`, `Program.cs` |
| Serialisation | `System.Text.Json` | `stream-json` lines, `gh` / `az` JSON output | where read |
| YAML of tickets and specs | YamlDotNet (16.3.0 in `Graph/GraphNet`) | Already used by the .NET ticket graph | `Spec/` |
| Data access | EF Core with `Npgsql.EntityFrameworkCore.PostgreSQL` | Schema in C#, `jidota init` applies the migrations; aggregates in LINQ, raw SQL when needed | `Data/` |
| Resilience | Polly | Retry with backoff around `gh`, `az`, `git` network calls (§7.1) | `Hosts/` |
| Logging | `Microsoft.Extensions.Logging` + Serilog (file sink, JSON) | One JSON file per day, filterable by `job_id` / `run_id` | `Program.cs` |
| Processes | `System.Diagnostics.Process` (standard library) | Start, stream stdout, kill the whole tree (`Kill(entireProcessTree: true)`) | `Hosts/`, `Agents/` |
| Paths | `Environment.SpecialFolder.LocalApplicationData` (standard library) | `<data>` is `%LOCALAPPDATA%` on Windows, `$XDG_DATA_HOME` or `~/.local/share` on Linux; paths built with `Path.Combine`, never a hard-coded separator | `Program.cs` |
| Secret at rest | Windows: DPAPI (`System.Security.Cryptography.ProtectedData`); Linux: file mode 0600 (`File.SetUnixFileMode`) | PostgreSQL password readable by the current user only; on Linux, the same protection `gh` and `claude` give their own tokens. The Secret Service keyring was rejected: it needs an unlocked desktop session, so it fails on a headless server | `Cli/Init`, `Data/` |
| Validation | hand-written | Only ticket yaml and API inputs; rules are few and specific | `Spec/`, `Web/` |
| Metrics, tracing | none | One process, one user; the database is the metrics store (§10) | — |
| Rate limiting | none | No callers but the owner | — |
| Test runner, mocks | xUnit, NSubstitute | Unit tests of the state machine, round rules, masking | `tests/Jidota.Tests/` |
| Integration tests | Testcontainers (PostgreSQL) | Real database for the data module and the recovery path | `tests/Jidota.Tests/` |
| Component tests (dashboard) | bUnit | Renders a Blazor component without a browser, clicks and types into it, with fakes for its services: covers the actions (confirmation before cancel, the rework note, refusal messages) and the live updates that a prerendered page cannot show. Playwright was rejected: browsers to install in the pipeline, slower and more fragile, for a single-user page | `tests/Jidota.Tests/` |
| End-to-end without tokens | fake `claude` executable | Replays a recorded `stream-json` and writes the expected job file | `tests/Jidota.Tests/` |

**Rejected:** Octokit and the Azure DevOps .NET client with stored PATs — two more secrets to keep
and renew, for calls the `gh` / `az` sessions already make. Dapper with SQL scripts — the mapping
and the migration runner would be written by hand. A static JS page polling the API, as
`dashboard.html` does today — the replay and comparison views would all be hand-written JS.

---

## 3. Boundaries

**Inside** — the job loop, the scheduler, the records in PostgreSQL, the `jidota` folder
(`<data>/jidota/`: configuration, clones, worktrees, job folders, logs), the job branches
`factory/<job-id>` and the draft PRs it opens, the Status of tickets with an open job.

**Outside**

| External system | Direction | `jidota` assumes |
|---|---|---|
| `claude` CLI | `jidota` starts it | Signed in with the owner's subscription; supports `-p`, `--append-system-prompt-file`, `--model`, `--tools`, `--settings`, `--setting-sources`, `--strict-mcp-config`, `--permission-prompts`, `--session-id`, `--resume`, `--add-dir`, `--output-format stream-json --verbose`, `--max-budget-usd` (all listed by `claude --help`, 2.1.332) |
| GitHub Project + issues (`gh`) | `jidota` calls it | `gh` signed in with the `project` scope; the Project has a single-select Status field |
| Code repositories, Azure DevOps Repos or GitHub (`git`) | `jidota` clones, fetches, pushes the job branch | The owner's git credentials can clone and push |
| PRs on GitHub (`gh`) or Azure DevOps (`az repos pr`) | `jidota` creates, updates, reads state | `az` signed in with the `azure-devops` extension for ADO hosts |
| Docker | `jidota init` creates or reuses the PostgreSQL container | Docker is running |
| PostgreSQL (container) | `jidota` reads and writes | Listens on `127.0.0.1` only |
| Interactive skills (spec factory, branch-to-pr, workitems) | call `jidota spec …`, `jidota pr …`, `jidota workitems …` | Run in a Claude Code session in the owner's working copy |
| Browser | calls the local API and dashboard | Same machine |

```
                 owner (browser, terminal)
                        │ HTTP 127.0.0.1 + token
                        ▼
 GitHub Project ◀─gh─  jidota  ─docker─▶ PostgreSQL (127.0.0.1)
 GitHub / ADO PRs ◀gh/az┤ │ ├─git─▶ clones + worktrees (<data>/jidota)
                        │ └─claude -p (one process per agent run, cwd = worktree)
                        │        reads/writes job files, commits on factory/<job-id>
 interactive skills ──▶ jidota spec | pr | workitems (no running instance needed)
```

**Trust boundaries** — ticket and spec bodies are written by people and read from GitHub; the
code of a repository and the output of its build and tests are not trusted either; agent output
(job files, tool results, the `stream-json` lines) is untrusted data. All of it is data, never
instructions to `jidota`, and it reaches the agents only as files (§9.2).

---

## 4. Components

| Component | Responsibility |
|---|---|
| `Cli/` | Parses commands; local commands run in-process, job commands call the API of the running instance |
| `Cli/Init` | `jidota init`: prerequisites, configuration, Status options, PostgreSQL container, migrations |
| `Web/` | Local API (§6) and the Blazor Server dashboard; checks the token |
| `Poller/` | Every poll interval: reads the Project, lists eligible tickets, reads the state of open PRs |
| `Jobs/` | The job state machine and the scheduler: slots, touches, transitions, human actions |
| `Agents/` | Starts one agent run (`claude -p`), streams its output to `Recording/`, enforces timeout and budget |
| `Agents/Settings` | Generates the `--settings` file of each code repository (allowed tools and commands, web tools denied) |
| `Recording/` | Masks each raw line, stores it, extracts tool calls and the run totals |
| `Hosts/Git` | Clones, fetches, creates and removes worktrees, reads HEAD and status |
| `Hosts/GitHub` | `gh`: Project items and Status, issues, sub-issues, PRs |
| `Hosts/AzureDevOps` | `az`: PRs and their work item links, work items for `WorkItems/` |
| `Hosts/Docker` | Creates, starts and inspects the PostgreSQL container |
| `Spec/` | `jidota spec fetch | graph | publish`, ported from `fetch_source.py`, `ticket_graph.py`, `publish_github.py` |
| `BranchToPr/` | `jidota pr collect | open`, ported from `branch_to_pr.py` |
| `WorkItems/` | `jidota workitems target | check | create`, ported from `workitems.py` |
| `Data/` | EF Core context, entities, migrations |

### The job state machine

| Stage | `jidota` does | Next |
|---|---|---|
| created | `git fetch`; worktree from `origin/<start_branch>` on branch `factory/<job-id>`; writes `spec.md` (job table, dependencies, raw ticket and spec, as `new_job` does today); Status In Progress | build |
| build | starts `jidota:builder` (mode build); reads the first line of `build.md` | `STATUS: DONE` → review(1); `STATUS: BLOCKED` → blocked |
| review(n) | creates `round-<n>/`; starts every reviewer at once; waits for all | rules of `round_cmd` in `factory.py`: file missing or first line malformed → that reviewer sent back once; all `PASS` → approve; any `CHANGES` with rework rounds left → rework; otherwise needs-human |
| rework | resumes the builder session (`--resume`) in mode rework with the round folder; a fresh builder if it cannot be resumed | review(n+1) |
| approve | starts `jidota:approver`; reads the first line of `decision.md` | `APPROVE` → pr; `ESCALATE` → pr with the reasons on top, then needs-human |
| pr | pushes `factory/<job-id>`; opens or updates the draft PR; links the `(scope)` work items on an ADO host; Status In Review | PR merged → done; PR closed → needs-human |
| blocked, needs-human | Status Needs human; waits for a human action | approve → pr; rework → rework (round from `review-human.md`) |
| done | Status Done; spec Done when all its tickets are Done | — |
| cancelled | process tree killed, draft PR closed, worktree removed, branch kept; Status Todo | — |

A human rework writes `round-<n>/review-human.md` (`VERDICT: CHANGES` and the note), resets the
rework count, and then runs a full review round, as step 7 of the current `SKILL.md` does.

### One agent run

```
claude -p "Mode: build. Job folder: <job folder>. Worktree: <worktree>"
  --append-system-prompt-file <job folder>/system-<agent>.md
  --model <model of the agent file>
  --tools <tools of the agent file>
  --settings <data>/jidota/settings/<repo>.json
  --setting-sources user --strict-mcp-config
  --permission-prompts none
  --session-id <uuid chosen by jidota>        (rework: --resume <builder session id>)
  --add-dir <job folder>
  --output-format stream-json --verbose
  --max-budget-usd <budget>
```

`jidota` builds the instructions itself instead of relying on `--agent` and `--plugin-dir`, so
that what an agent receives does not depend on how Claude Code loads a plugin's agents, and no
plugin is loaded for a run:

- **The system prompt** is appended to Claude Code's default one (which keeps its tools and the
  repository's `CLAUDE.md`). `jidota` writes it to `system-<agent>.md` in the job folder, from two
  parts: a header that says where the agent works (code repository, branch `factory/<job-id>`,
  worktree, job folder, running unattended: no one can answer a question during the run), then
  the body of `Factory/agents/<agent>.md` after its front matter.
- **The front matter** of the agent file gives `--model` (`model`) and `--tools` (`tools`, the
  built-in tools made available). Which Bash commands may run is decided by the generated
  `--settings`, not by `--tools`.
- **The task** is the prompt argument: the prompt of the current `SKILL.md`, paths only, so it
  stays short. It is passed through `ProcessStartInfo.ArgumentList`, never a shell string. Stdin is
  not used: the docs do not say what `claude -p` does with no prompt argument.
- **`--permission-prompts none`**: since v2.1.302, `claude -p` starts in Manual mode, where a call
  that needs approval is denied or waits for a permission host. With this flag, the call is
  denied at once, the model is told not to retry, and the run goes on. The denial shows as a
  `system` / `permission_denied` message and in `permission_denials` of the `result` message,
  which the docs call the authoritative record; `jidota` reads it there (§7.1).
- **`--setting-sources user --strict-mcp-config`**: without `--bare`, `claude -p` runs the hooks of
  the code repository's `.claude/settings.json` and the servers of its `.mcp.json` with no trust
  dialog. The code repository is untrusted (§3): its settings, hooks and MCP servers are not
  loaded. `--bare` is not used: it does not read `CLAUDE_CODE_OAUTH_TOKEN` and skips the
  repository's `CLAUDE.md`, which agents follow.

The process runs with the worktree as its working directory. The agent files stay the only
source of the agents' instructions: `jidota` reads them from the plugin folder packaged with the
tool, and never edits them. Recording the assembled `system-<agent>.md` in the job folder shows,
for every run, exactly which instructions the agent had.

On a `--resume`, Claude Code sends the system prompt recorded at the first launch of the session,
even if a later launch passes other text (`--system-prompt-snapshot`, on by default): a rework
keeps the builder's instructions of its build run.

**Privilege rules**

- `Jobs/` is the only writer of a job's stage, and of the Status of a ticket with an open job.
- `Hosts/Git` is the only component that pushes, and it pushes `factory/<job-id>` only.
- `Recording/` is the only writer of runs, tool calls and raw lines, and masks before writing.
- Agents write only in their job folder and in their worktree.
- `Data/` holds the only `DbContext`; other modules go through it.

---

## 5. Data

| Entity | Owned | Lives in | Lifecycle |
|---|---|---|---|
| Configuration | yes | `<data>/jidota/config.json` | Written by `jidota init`, read by every command and by the spec factory subcommands |
| Secrets | yes | `<data>/jidota/secrets.json` | PostgreSQL password, written by `jidota init` (§9.3) |
| Clone | yes | `<data>/jidota/clones/<host>/<repo>/` (folder set at init) | Created at the first job of a repository; kept; fetched before each job |
| Worktree | yes | `<data>/jidota/worktrees/<job-id>/` | Created with the job; removed at cancel or by `jidota clean` once the job is done, never with uncommitted changes |
| Job folder | yes | `<data>/jidota/jobs/<job-id>/` | Created with the job; kept |
| Job | yes | table `jobs` | One per started ticket; stage updated at each transition; never deleted |
| Job event | yes | table `job_events` | One per transition and per human action (who, when, note); append-only |
| Review round | yes | table `review_rounds` | One per round, with each reviewer's verdict |
| Agent run | yes | table `agent_runs` | Row created before the process starts (`running`); closed with its end status and totals |
| Tool call | yes | table `tool_calls` | One per `tool_use` / `tool_result` pair of a run |
| Raw line | yes | table `run_lines` | Every masked `stream-json` line, in order; kept with no time limit |
| Job result | yes | tables `jobs`, `pull_requests`, `job_work_items` | Diff, commits, test counts, outcome, PR state and merge commit, linked work items |
| Ticket, spec | no | GitHub issues in the Project | Read at each poll; the job keeps a copy in `spec.md` |
| Ticket Status | written while a job is open | GitHub Project | See §4 |
| Work item | no | ADO or GitHub, referenced by the spec's `sources` | Only its reference and title are stored |

Per run, `agent_runs` holds: job, agent, round, session id, model, input / output / cache-creation /
cache-read tokens, `total_cost_usd`, `num_turns`, `duration_ms`, `duration_api_ms`, starting commit
(repository, HEAD, clean or dirty), end status (`finished`, `timeout`, `budget`, `crashed`,
`cancelled`, `quota`, `auth`, `permission_denied`). Totals come from the `result` message; a run
without one keeps the tokens counted up to its last message and no cost.

The job id is `<seq>-<ticket id>-<slug>` as in `factory.py`, with one sequence across all
repositories.

**Schema** — EF Core entities in `Data/`, migrations in `Data/Migrations/`. `jidota init` applies
the pending migrations; the running instance refuses to start on a database behind its migrations.

**Integrity** — a transition is one transaction: stage, job event and any Status to write are
committed together, and the Status write to GitHub happens after the commit (§7.1). Raw lines are
written as they arrive, so a crash keeps everything received.

---

## 6. API contract

### Commands

| Command | Needs a running instance | Effect |
|---|---|---|
| `jidota init` | no | Configuration, Status options, PostgreSQL container, migrations, prerequisites |
| `jidota start` | no | Starts the instance in the background and gives the terminal back |
| `jidota stop` | yes | Drain: no new run; each running run finishes; then the process exits |
| `jidota status` | no | Running or not, paused or not, running jobs, free slots, last poll, dashboard URL |
| `jidota resume` | yes | Ends a pause on quota or auth |
| `jidota run <ticket \| spec>` | yes | Starts now what the poller would start (Ready, dependencies Done, touches, slots) |
| `jidota approve <job>` | yes | needs-human job → draft PR opened or updated |
| `jidota rework <job> <note>` | yes | needs-human, blocked or pr job → rework with the note |
| `jidota cancel <job>` | yes | Cancels the job (§4) |
| `jidota clean` | no | Removes the worktrees of done and cancelled jobs, never one with uncommitted changes |
| `jidota spec fetch \| graph \| publish …` | no | Ported spec factory scripts, same inputs, outputs and exit codes |
| `jidota pr collect \| open …` | no | Ported `branch_to_pr.py` |
| `jidota workitems target \| check \| create …` | no | Ported `workitems.py` |

`jidota start` starts the same executable detached, with an internal `serve` command. A command
that needs a running instance and finds none says so and exits 6.

### Local API

Listens on `127.0.0.1` only, on the port of `config.json`. Every call carries the token that
`jidota start` writes to `<data>/jidota/api.token` (owner-only, like `secrets.json`): the CLI sends it as a header; the
dashboard URL given by `jidota status` carries it once and sets a cookie.

| Route | Effect |
|---|---|
| `GET /api/status` | Instance state, jobs, slots, last poll |
| `POST /api/jobs` `{ "target": "<ticket or spec issue URL>" }` | `jidota run` |
| `POST /api/jobs/{id}/approve` | `jidota approve` |
| `POST /api/jobs/{id}/rework` `{ "note": "…" }` | `jidota rework` |
| `POST /api/jobs/{id}/cancel` | `jidota cancel` |
| `POST /api/stop`, `POST /api/resume` | `jidota stop`, `jidota resume` |

The dashboard calls the same routes: a human action has one code path whichever way it comes.

### Errors

| HTTP | CLI exit | Meaning | Retryable |
|---|---|---|---|
| 200 / 202 | 0 | Done / accepted | — |
| — | 1 | Error (message on stderr) | depends |
| 422 | 2 | `[HUMAN]` ticket | no |
| 409 | 3 | The ticket already has an open job, or the job is not at a stage that allows the action, or a run is active | no |
| 422 | 4 | Not eligible: Status not Ready, or a dependency not Done (the list is returned) | after the dependency |
| 409 | 5 | Busy: touches overlap an open job of the same repository, or no free slot | yes, later |
| 401 | 1 | Missing or wrong token | no |
| 404 | 1 | Unknown job or issue | no |
| — | 6 | No running instance | after `jidota start` |

Exit codes 0 to 5 keep the meaning they have in `factory.py`.

**Compatibility** — the ported subcommands keep the inputs, outputs and exit codes of their Python
script, because the `SKILL.md` files of the interactive skills route on them. The local API has a
single client version, the one installed with it; it is not versioned.

---

## 7. Failure and recovery

### 7.1 Retry

| Failure | Behaviour |
|---|---|
| `gh`, `az`, `git` network error, timeout, 5xx, GitHub rate limit | 3 attempts, increasing delay (Polly). Then by action: a poll is skipped (the next one catches up); a Status write is redone at the next poll; a push or PR creation sends the job to needs-human |
| Agent run: timeout or budget exceeded | Run ends `timeout` / `budget`; restarted once; second failure → needs-human |
| Agent run: process crash, or `jidota` crash during the run | Run ends `crashed`; restarted once; second failure → needs-human |
| Agent run: quota of the subscription reached | Seen in the `rate_limit_event` lines of `stream-json` (`status: rejected`, with `resetsAt`). Run ends `quota`; global pause: no run starts; the job stays at its stage; `jidota` resumes on its own at `resetsAt`, or every 30 min when the event gives no time. An `allowed_warning` event (near the limit, with `utilization`) is shown on the dashboard and starts nothing new above the threshold of `config.json` |
| Agent run: `claude` session expired | Run ends `auth`; global pause until `jidota resume`, after a new `claude` sign-in |
| Agent run: a permission denied by the settings | Read from `permission_denials` of the `result` message. Run ends `permission_denied`; job → needs-human with the denied tool and its input |
| Agent file missing or first line malformed | Agent sent back once; second time → needs-human (as today) |
| Builder session cannot be resumed | Fresh builder with the same prompt |

**Never retried:** 401, 403 and 404 from `gh` / `az` (access does not come back by retrying; the
job goes to needs-human with the cause), invalid ticket yaml, unknown dependency.

### 7.2 Rollback

None. Commits on the job branch, a pushed branch, an opened PR and a Status write are not undone.
What is guaranteed instead: each step is idempotent on re-run. A job resumed after a restart
reuses the worktree recorded for it in the database (a worktree folder no job owns is never
reused: §11), an
open PR of the branch is updated rather than duplicated (`find` then `update`, as `pr_cmd` does),
a Status that already has the right value is left alone. Cancel is the compensating action for a
whole job (§4).

### 7.3 Recovery

On `jidota start`, after a stop, a crash or a reboot:

1. Runs still `running` in the database have no process: they end `crashed`.
2. Each job not in done, cancelled, needs-human or blocked resumes at its stage: a crashed run is
   restarted once (§7.1); a job between two runs starts its next run.
3. The Status of every ticket with an open job is written again from its job.

The operator only runs `jidota start`. A job left in needs-human by the recovery is released with
`jidota approve` or `jidota rework`.

### 7.4 Concurrency

- **One instance per machine.** `serve` takes a PostgreSQL advisory lock at start and refuses to run
  without it. One instance per Project across machines is a non-goal and not guarded.
- **Running jobs** (stages created, build, review, rework, approve) never exceed the parallel-jobs
  limit, across all repositories. Jobs at pr, needs-human or blocked take no slot.
- **Touches** — two open jobs of the same repository never have overlapping `touches` (rules of
  `overlap()` in `factory.py`: a path ending with `/` covers what is under it); a ticket with no
  `touches` runs alone in its repository. A job not done or cancelled still holds its files.
- **Scheduler decisions are serialized** in the process: eligibility, slot and touches checks and
  the creation of the job happen under one in-process lock and one transaction, whether the
  request comes from the poller, the CLI or the dashboard.
- **Within a job**, reviewers run in parallel; nothing else does.
- **Git** — no checkout under the scheduler lock (`git worktree add --no-checkout`, then fill the
  worktree outside it), as `new_job` does: on a large repository a checkout would hold every other
  decision. Agents never use `git stash`, which is shared by every worktree of a clone.

---

## 8. Performance and limits

### 8.1 Latency

**N/A** — no target. A job takes as long as its agent runs; build and test commands of the code
repository dominate. A Ready ticket starts within one poll interval when a slot is free.

### 8.2 Throughput

Up to the parallel-jobs limit (3) running at once, each with up to two reviewers in parallel. The
bottleneck is the subscription quota, not the machine.

### 8.3 Limits

| Limit | Value | At the limit |
|---|---|---|
| Poll interval | 5 min (`config.json`) | — |
| Parallel jobs | 3 (`config.json`) | Ticket stays Ready, starts when a slot frees |
| Max rework rounds | 2 (`config.json`) | needs-human |
| Reviewers | security, code (`config.json`) | — |
| Run duration | 60 min (`config.json`) | Process tree killed, run `timeout` |
| Run budget | 10 USD, `--max-budget-usd` (`config.json`) | Run `budget` |
| Quota retry | at `resetsAt` of the `rate_limit_event`, else every 30 min | Pause continues |
| Quota warning threshold | **Not decided** — `utilization` above which no new run starts | — |
| Retry of CLI calls | 3 attempts | §7.1 |
| ADO PR description | 4000 characters (`ADO_DESCRIPTION_MAX` in `factory.py`) | Truncated with a pointer to the job folder |
| Raw output retention | none | Kept forever |
| API and dashboard port | **Not decided** — set in `config.json` by `jidota init`; default to choose | — |
| PostgreSQL image and version | **Not decided** — chosen when `Hosts/Docker` is written | — |
| Log file retention | **Not decided** — Serilog keeps every daily file until a limit is set | — |

---

## 9. Security

### 9.1 Identity

- `jidota` runs as the owner's user, in the background, started by `jidota start`, on Windows and
  Linux. macOS is not excluded by the code, but is neither tested nor supported.
- `claude`, `gh`, `az` and `git` use the owner's own sessions and credentials. `jidota` holds none of
  their tokens.
- PostgreSQL: user and random password generated by `jidota init`, password stored in
  `secrets.json`, DPAPI-encrypted for the current user on Windows, mode 0600 on Linux.
- Callers of the API authenticate with the token of `api.token`, regenerated at each `jidota start`.
- Agents run with the permissions of the generated `--settings` of their repository: the tools
  allowed, the build and test commands, web tools denied. In print mode no one can approve a
  prompt; a denial ends the job in needs-human (§7.1).
  **Not decided** — where the allowed build and test commands of each repository come from (a
  section per repository in `config.json`, a file in the code repository, or the tickets' How to
  check). The content of the generated settings, and so the first jobs of each repository, depend
  on it.
- Agents run on the owner's machine, filtered by the allowlist but not isolated: a command the
  allowlist accepts can read anything the owner can.
  **Not decided** — a sandbox. The options found in the Claude Code docs (2026-11-28):

  | Option | Isolates | Windows | Linux | Cost |
  |---|---|---|---|---|
  | Built-in sandbox (`sandbox.enabled` in the generated settings) | Bash only: writes limited to the worktree, added folders and temp; network through a proxy to allowed domains. Reads stay open by default (`sandbox.filesystem.denyRead` needed for `~/.ssh` and credentials); Read, Edit, Write follow permission rules only | Not native ("runs commands unsandboxed"); WSL2 only | Yes, needs `bubblewrap` and `socat` | A few settings keys |
  | Docker container per run | Everything (Bash, file tools, hooks, MCP); the documented setting for `--dangerously-skip-permissions` | Linux containers only: no Windows-only build | Yes | One image per toolchain; auth by `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token`, one year), which a run can read and exfiltrate |
  | `srt` sandbox runtime | The whole process | Not native | Yes | Beta |

  The choice changes the generated settings, the prerequisites checked by `jidota init`, and, for
  a container, how `Agents/` starts a run.

### 9.2 Input

**Untrusted inputs** — ticket and spec bodies, the yaml in them, `code_repo` and `start_branch`
values, the code and build output of the repository, every agent file and `stream-json` line, API
request bodies.

**Validation** — ticket yaml is parsed with YamlDotNet into typed fields before any side effect:
`id`, `depends_on`, `code_repo`, `start_branch`, `touches`. `code_repo` must match a GitHub or
Azure DevOps remote pattern (`ORIGIN_GH`, `ORIGIN_ADO`, `ORIGIN_ADO_SSH`, `ORIGIN_VS` of
`factory.py`), otherwise needs-human "unknown host".

| Surface | Mitigation |
|---|---|
| Prompt injection through ticket text | Prompts carry paths only; agents treat the copied ticket and spec as data (wording already in `spec.md` and the agent files) |
| Shell injection through ticket values | Every process is started with an argument list, never a shell string; values never reach a shell |
| Path traversal through `touches` or the job id | Job id built by `jidota` from the ticket id and a slug of `[a-z0-9-]`; `touches` are only compared, never used to open files |
| Option injection (`start_branch` starting with `-`) | Branch and URL values are validated before use and passed after `--` where git accepts it |
| Text sent to `gh` / `az` (PR body, titles) | Always through a file (`--body-file`, `--description @file`), as the scripts do today |
| HTML in the dashboard | Blazor encodes rendered text; raw output and markdown are shown as text |
| Cross-site calls to the local API | Token required on every route |

**Invalid input** — the ticket goes to needs-human with the reason; the value is logged truncated,
never executed.

### 9.3 Secrets

| Secret | Source | Unlocks |
|---|---|---|
| PostgreSQL password | generated by `jidota init`, in `secrets.json` (DPAPI on Windows, 0600 on Linux) | the JidoTa database |
| API token | generated by `jidota start`, `api.token` | the local API and dashboard |
| `claude`, `gh`, `az` sessions | the owner's sign-ins, held by each CLI | the subscription, GitHub, Azure DevOps |

**Masked before a raw line is stored:** values of environment variables whose name looks like a
secret (`TOKEN`, `KEY`, `SECRET`, `PASSWORD`, `PAT`…) and are at least 8 characters long, the `gh`,
`az` and `claude` tokens, the PostgreSQL connection string.

**Must never appear in:** the database (raw lines, tool calls, job files copied), the logs, the
PR bodies, the dashboard, error messages, terminal output.

---

## 10. Observability

| Signal | Answers |
|---|---|
| Dashboard | What runs, what waits for a human, what a work item cost |
| `agent_runs`, `tool_calls`, `run_lines` | What an agent did, step by step, and what it cost |
| `job_events` | Why a job is where it is, and who acted on it |
| Log files | Why `jidota` did or did not do something (poll, CLI errors, Status writes) |
| `jidota status` | Is it running, paused, how many slots are free, when was the last poll |

### 10.1 Logs

Serilog, compact JSON, one file per day in `<data>/jidota/logs/`. Every line of a job carries
`job_id`, and of a run `run_id` and `session_id`.

- `Information`: poll done (tickets seen, started), each transition, each human action, each Status
  write, pause and resume.
- `Warning`: retried CLI call, Status restored after a manual change, ticket ignored and why.
- `Error`: failed CLI call after retries, run ended other than `finished`.
- `Debug`: the CLI commands run (arguments only, never their output).

Never logged: secrets, the output of agent runs (it is in `run_lines`), ticket bodies.

### 10.2 Tracing

**N/A** — one process. The job id, run id and session id correlate the logs, the database and the
`claude` session; there is no distributed tracing.

---

## 11. Edge cases

### Caught at validation — nothing is written

| Case | Behaviour |
|---|---|
| Ready ticket with no `id` in its first yaml block, or malformed yaml | Ticket → Needs human, reason "invalid ticket yaml"; no job |
| `depends_on` naming no ticket of the spec | Ticket → Needs human, reason with the unknown id |
| `[HUMAN]` ticket set to Ready | Ignored, `Warning` log; as a dependency it is done when its Status is Done |
| Spec issue (yaml `child_specs`) in the Project | Never started; its Status is derived from its tickets |
| Closed issue with Status Ready | Ignored |
| `approve` on a job not in needs-human, `rework` on a job not in needs-human / blocked / pr | 409, exit 3 |
| `rework` or `approve` while a run of the job is active | 409, exit 3 |
| Manual `run` of a ticket not Ready or with a dependency not Done | 422, exit 4, with the dependencies |

### Caught before the side effect

| Case | Behaviour |
|---|---|
| `code_repo` cannot be cloned (no access, unknown host) | Ticket → Needs human with the cause; no job branch |
| `start_branch` missing on `origin` | Ticket → Needs human |
| The worktree folder of a new job already exists on disk (no job of the database owns it) | No job is created, nothing is written in that folder; ticket → Needs human, reason "worktree `<path>` already exists". Needs human rather than a plain error, as in `factory.py`, because the poller would otherwise retry it at every poll. A human removes the folder and sets the ticket to Ready again |
| Touches overlap an open job of the same repository, or no free slot | Ticket stays Ready; started at a later poll |
| A ticket Ready again while its job is open | Status put back to the job's Status, `Warning` log |
| Status changed by hand on a ticket with an open job | Put back at the next poll; only `cancel` stops a job |

### Runtime

| Case | Behaviour |
|---|---|
| Filling the worktree fails (`git reset --hard` after `git worktree add --no-checkout`: disk full, path too long, file locked) | The job and its branch exist: job → needs-human, reason "checkout of the worktree failed: `<git message>`", as `factory.py` does. No agent runs. The human fixes the cause and cancels the job, then sets the ticket to Ready again |
| Agent wrote no file or a malformed first line | Sent back once, then needs-human |
| Run timeout or budget | Run `timeout` / `budget`, restarted once, then needs-human |
| Quota or auth | Global pause (§7.1) |
| Permission denied | needs-human with the command |
| `jidota` crashes during a run | Run `crashed` at next start, restarted once |
| Push rejected | needs-human with the git message |
| An open PR already exists for the branch | Updated, not duplicated |
| PR closed without merge | needs-human, reason "PR closed without merge" |
| PR merged | done; spec Done when all its tickets are Done; dependents eligible at the next poll |
| PR in conflict with its start branch | Not detected; a human asks for a rework |
| `cancel` during a run | Process tree killed, run `cancelled`, then the cancel of §4 |
| `jidota stop` during runs | Waits for each run to finish; jobs carry on at the next start |
| ADO PR description over 4000 characters | Truncated with a pointer to the job folder |

### Traps already met

- A host rewrites the squash message of a merged PR: a dependency cannot be found by its commit
  subject after a host merge. Hence the Project Status as the only source of truth.
- `#33` must never match `#330`: references are compared whole, never by substring.
- `git stash` is shared by every worktree of a repository: agents never use it.
- `gh project` commands need the `project` scope (`gh auth refresh -s project`).
- A checkout under a shared lock blocks every other decision on a large repository: worktrees are
  added with `--no-checkout` and filled outside the lock.
- `claude -p` without a permission mode starts in Manual mode (v2.1.302+): a call that needs
  approval can wait for a permission host instead of failing. Always pass `--permission-prompts none`.
- `claude -p` loads the code repository's `.claude/settings.json` hooks and `.mcp.json` servers
  with no trust dialog: always pass `--setting-sources user --strict-mcp-config`.
- On `--resume`, the system prompt of the first launch is sent again, whatever the later launch
  passes (`--system-prompt-snapshot`).
- Stopping a run with SIGTERM gives exit 143 and no `result` message for the turn in progress:
  a cancelled run never has totals.

### To verify in the first spike

- `rate_limit_event` is documented in the Agent SDK reference (`rate_limit_info.status`:
  `allowed` | `allowed_warning` | `rejected`, `resetsAt`, `utilization`). Check against a real run
  the unit of `resetsAt` (seconds or milliseconds since the epoch), which the reference does not
  give. No undocumented field of this event is relied on.
- Whether `total_cost_usd` of a `--resume` run counts the resumed session only from that run, or
  from its start: the sum per job depends on it.
- On Linux, that the instance started by `jidota start` is detached from the terminal (its own
  session, as `setsid` gives) and survives the terminal being closed.
- Adding In Review and Needs human to the Status field: the GraphQL mutation, and that existing
  items keep their value.

---

## 12. Invariants

A change that breaks one of these is a defect, however convenient it looks.

1. While a job is open, only `jidota` writes the Status of its ticket, and Done is written only
   when the PR is merged.
2. `jidota` pushes only `factory/<job-id>`, never with force. Every PR it opens is a draft; it never
   marks one ready, approves or merges it.
3. An agent run has its `agent_runs` row, status `running`, before its process starts.
4. A job transition is committed to the database before the next agent run starts.
5. An agent prompt holds paths only, never the text of a ticket, a spec or a review.
6. The next stage of a job is decided from the first line of the file the agent wrote, never from
   the agent's reply.
7. A raw line is masked before it is written to the database.
8. Running jobs never exceed the parallel-jobs limit; two open jobs of one repository never have
   overlapping `touches`.
9. The job loop runs commands only in clones and worktrees under the `jidota` folder, never in a
   working copy it did not create.
10. A worktree with uncommitted changes is never removed.
11. No secret appears in the database, the logs, a PR body or the dashboard.
12. The ported subcommands keep the inputs, outputs and exit codes of the scripts they replace.
13. Every agent run is started with `--permission-prompts none`, `--setting-sources user` and
    `--strict-mcp-config`, and never with `--dangerously-skip-permissions` while runs are not
    isolated.
