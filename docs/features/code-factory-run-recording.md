# Code factory run recording — features

Features to bring into JidoTa. The code factory runs on its own, with no Claude Code session: it
picks up Ready tickets, starts each agent as its own `claude -p` process, and delivers each ticket
as a draft pull request. Every agent run, the result of every job and the link to the ADO work item
it implements are recorded, and all of it is readable from a local dashboard: what runs now, what
waits for a human, what each work item cost, and how each agent worked, step by step.

Prepared on 2026-11-28. Not yet created in Azure DevOps.

Decisions behind these features:

- Purpose: cost per work item, traceability / audit, improving the agents, measuring productivity.
- Single reader: the owner of JidoTa.
- The code factory moves to `claude -p` first; the spec factory stays interactive and is not
  recorded for now (not even the ADO work items it reads).
- Storage: PostgreSQL, local, in Docker. Raw run output kept with no time limit, secret values
  masked.
- "Commits used for the analysis" means the starting commit the agent read the code at.
- Cost is the `total_cost_usd` reported by `claude -p`, an estimate on a subscription token.
- JidoTa creates and reads its specs and tickets in one GitHub Project, which holds tickets for
  several code repositories (OeeService, Refrakt…). A spec has one code repository.
- All of JidoTa (poller, job loop, recording, dashboard) is one .NET tool, `jidota`, which
  replaces `factory.py`.
- Delivery is always a draft pull request. The local squash-merge of `factory.py` is dropped.
- The GitHub Project is the only work queue: only published tickets (GitHub issues) are run.
  Local tickets (`specs/<slug>/tickets/T<n>.md`), `factory/backlog.md` and `next` are dropped,
  and so are `factory/board.json` and the old `dashboard.html`.
- `jidota` sets a ticket to Done when its PR is merged: the human's merge is the approval. This
  replaces "Done is always set by a human" (README, design of 2026-10-15).
- JidoTa has one configuration, written by `jidota init`. The spec factory reads it and stops with
  an error when `jidota init` has not been run.
- No Python is left: every script of the plugin (`factory.py`, the spec factory scripts,
  `branch_to_pr.py`, `workitems.py`) becomes a subcommand of `jidota`.
- The `/jidota:code-factory` skill is removed: `jidota` is the orchestrator. Its agents (builder,
  security-reviewer, code-reviewer, approver) stay in the plugin, packaged with `jidota`, which
  reads them to build the instructions of every `claude -p` run.
- `/jidota:spec-factory`, `/jidota:workitems` and `/jidota:branch-to-pr` stay as interactive
  skills; their `SKILL.md` calls `jidota` instead of `python`. `/jidota:branch-to-pr` is for
  branches made by hand: the PR of a job is built by `jidota` from the job files.

---

# Feature: Code factory runs unattended and records every agent run

## 1. Description
Today the code factory runs inside an interactive Claude Code session. That session starts the
builder, the reviewers and the approver as sub-agents, and nothing records what each of them
consumed. With this feature, the `jidota` .NET tool runs the code factory loop with no Claude Code
session. It starts each agent as its own `claude -p` process, in the job's worktree, with the
agent's instructions and a short task that names the job files. Nothing waits on a person between
two agents, and each run can be measured, limited and stopped on its own. Each agent run is
recorded in a local PostgreSQL database: tokens, the tools Claude called, the time spent, the
commit the agent read the code at, and the full raw output of the run.

## 2. Scope
**In scope:**
- The `jidota` .NET tool runs the code factory loop with no Claude Code session: build, reviewers
  in parallel, rework rounds, approver, draft PR, parallel jobs. It replaces `factory.py`.
- Builder, reviewers (security, code) and approver run as separate `claude -p` processes, with the
  instructions of their agent file, in the job's worktree, and write the same files as today (`build.md`, `review-<name>.md`,
  `decision.md`).
- A rework round resumes the builder's session (`claude -p --resume`), so it keeps its context. If
  the session cannot be resumed, a fresh builder starts from `build.md` and the round folders. Each
  resumption is a run of its own, linked to the same session.
- Permissions with no human to approve them: `jidota` generates the settings of each code
  repository (`--settings`): the tools allowed, the build and test commands, web tools denied.
  A command refused by these settings fails the run, and the job goes to needs-human. Each run has
  a timeout and a budget (`--max-budget-usd`).
- For each agent run, these are recorded:
  - the job, the agent, the rework round and the session;
  - the model used;
  - input, output, cache-creation and cache-read tokens;
  - the cost reported by `claude -p`;
  - the number of turns, the wall-clock time and the API time;
  - every tool call (tool name, input, result, success or failure, time);
  - the starting commit (code repository, HEAD, clean or dirty worktree);
  - how the run ended: finished, or failed (timeout, crash, cancelled, quota or auth).
- A run that does not finish is recorded too: its end status, the raw output received so far and
  the tokens counted up to its last message. It has no cost, since `claude -p` reports none.
- The full raw output of every run is stored with secret values masked, and kept with no time
  limit. Masked: the values of environment variables whose name looks like a secret (`TOKEN`,
  `KEY`, `SECRET`, `PASSWORD`, `PAT`…) and are at least 8 characters long, the `gh`, `az` and
  `claude` tokens, and the PostgreSQL connection string.
- PostgreSQL runs locally in Docker.

**Explicitly out of scope:**
- The spec factory (spec-writer, ticket-writer). It stays interactive and is not recorded for now.
  Its only changes are that its scripts become `jidota` subcommands and that it reads the
  configuration of `jidota` (see "JidoTa operated from one command").
- Snapshots of the ADO work items read to build specs and tickets. Only the reference is kept
  (see "Every implemented ticket keeps its result").
- Commits Claude looks at during a run. Only the starting commit is recorded.
- The JidoTa daemon designed on 2026-10-15 (Linear, Windows service). Polling of the GitHub Project
  is covered by "Ready tickets picked up from the GitHub Project".

## 3. Success Criteria
- Every code factory job has a record of each of its agent runs, finished or not, with no
  exception.
- The tokens, cost, turns and durations stored for a finished run match the totals `claude -p`
  reports at the end of that run.

---

# Feature: Every implemented ticket keeps its result

## 1. Description
Today, the result of a job is spread across `build.md`, the review files, `decision.md`, the board
and git, and nothing links it back to the work item it came from. With this feature, each job
stores its result in the same database, together with the ticket, the spec and the ADO work items
it implements.

## 2. Scope
**In scope:**
- The diff produced, the commits of the job branch, the draft pull request and, once a human has
  merged it, its merge commit on the host.
- The tests run and their results (the passed, failed and skipped counts the builder already
  reports).
- Each review round: the verdict of each reviewer, the number of rework rounds, and the approver's
  decision.
- The final outcome of the job (done, needs-human, blocked, cancelled), its reason, and the pull
  request state.
- The link from job to ticket, to spec, and to every work item marked `(scope)` in the spec's
  `sources`: an ADO work item, or a GitHub issue when the spec came from one.
- On an Azure DevOps host, the draft PR is linked to the `(scope)` work items, as
  `/jidota:branch-to-pr` does. On a GitHub host, the PR description names them.

**Explicitly out of scope:**
- Contents of the ADO work item (fields, revision, children). Only its reference is kept.
- Writing anything on the work item itself.

## 3. Success Criteria
- Every finished job, whatever its outcome, has its result recorded and linked to its work items.

---

# Feature: Cost and time visible per work item

## 1. Description
Today there is no way to know what a work item cost to implement, or to look back at how an agent
worked. This feature adds a dashboard, served by a small local process, with three views:

- **Jobs**: every job as a card at its stage (build, review, approve, PR, done), the jobs that wait
  for a human with their reason, the running jobs against the parallel-jobs limit, and the cost of
  each job so far.
- **Spending**: cost, tokens and time per ADO work item, per ticket, per job and per agent, and
  their trend over time.
- **Run**: one agent run read back step by step, each tool call with its input and its result.

## 2. Scope
**In scope:**
- A small local process of the `jidota` tool serves the dashboard on localhost only;
  `jidota start` starts it.
- Cost, tokens and time totals per work item, its tickets, their jobs and each agent.
- A job linked to several `(scope)` work items counts in full for each of them. The dashboard marks
  these costs as shared, since their sum is more than the real total.
- Cost is the `total_cost_usd` reported by `claude -p`. On a subscription token it is an estimate,
  not a bill, and the dashboard labels it as such. Runs that did not finish have no cost and are
  shown as such.
- A replay view of one run, showing each tool call and its result, in order.
- Comparisons between runs (tools called, turns, failures), to improve the agents' prompts.
- Single user: the owner of JidoTa.

**Explicitly out of scope:**
- Sharing with the team or the client.
- Comparing actual time and cost with the work item's story points. Nothing is read from ADO.

## 3. Success Criteria
- The dashboard gives the cost, time and tokens of a work item, its tickets and their jobs.
- A run can be read back step by step from the database.

---

# Feature: Jobs started and released from the dashboard

## 1. Description
Today jobs are started with `/jidota:code-factory <ticket | spec | next>` and released with
`approve <job-id>` or `rework <job-id> <note>`, all typed in the session that runs the factory. With
no session left, these actions move to the dashboard. The `jidota` tool picks them up and carries
the job on.

## 2. Scope
**In scope:**
- From the dashboard, start a job for a ticket, or for the tickets of a spec, without waiting for
  the next poll. The rules are those of the poller: only tickets whose Status is Ready and whose
  `depends_on` are all Done, within the touches and parallel-jobs rules. For a spec, its tickets
  that meet these rules start.
- From the dashboard, approve a job in needs-human: `jidota` opens or updates its draft PR.
- From the dashboard, send a job in needs-human, blocked or with an open PR back to rework with a
  note.
- From the dashboard, cancel a job: the running `claude -p` process is stopped, the draft PR, if
  any, is closed, the worktree is removed, the job branch is kept, and the ticket goes back to
  Todo. A human sets it to Ready again to run it anew.
- Each human action is recorded with the job: who, when, the note.

**Explicitly out of scope:**
- Sharing the dashboard with other users.
- Starting a ticket that is not Ready or whose dependencies are not Done.

## 3. Success Criteria
- A job can be started or cancelled, and a job in needs-human or blocked released, from the
  dashboard without opening a Claude Code session.

---

# Feature: Ready tickets picked up from the GitHub Project

## 1. Description
Today the code factory is started by hand, from the root of one code repository, for one ticket,
spec or backlog line. With this feature, the `jidota` tool polls the GitHub Project that
JidoTa uses for its specs and tickets, every 5 minutes. It starts a job for each Ready ticket, in
the code repository that ticket names, and moves the ticket's Status as the job goes. The Project
holds tickets for several repositories (OeeService, Refrakt…), so one `jidota` serves all of them.

## 2. Scope
**In scope:**
- `jidota` polls the GitHub Project used by JidoTa every 5 minutes.
- A ticket is picked up when its Status is Ready and every ticket in its `depends_on` is Done. The
  Status of the Project is the only source of truth for dependencies: it replaces the check of the
  commit subject on `start_branch`. A `[HUMAN]` ticket is never picked up; as a dependency, it is
  done when its Status is Done.
- Spec issues (yaml `child_specs`) are never picked up.
- The job runs in the repository named by the ticket's `code_repo`, in Azure DevOps Repos or on
  GitHub. `jidota` clones each repository itself, keeps the clone, and creates the job
  worktrees in it.
- Delivery is always a draft pull request: `jidota` pushes the job branch and opens a draft PR
  into the ticket's start branch. A human merges it.
- `jidota` moves the ticket's Status:
  - Ready → In Progress when the job starts, and back to In Progress for a rework, including after
    the PR is open;
  - In Review when the draft PR is open or updated;
  - Needs human when the job is blocked, escalated (the draft PR is open, its escalation reasons
    on top) or out of rework rounds, when the PR is closed without being merged, or when the
    ticket's `code_repo` cannot be cloned or pushed (missing access, unknown host);
  - Todo when the job is cancelled;
  - Done when the PR is merged.
- `jidota` moves the spec's Status from its tickets: In Progress when the first of its tickets
  starts, Done when all its tickets are Done.
- `jidota init` adds In Review and Needs human to the Status field of the Project (today: Todo,
  Ready, In Progress, Done).
- Several jobs run at once, across all repositories and several in the same repository, as long as
  their `touches` do not overlap and the parallel-jobs limit (3 today, across all repositories) is
  not reached. Touches overlap only within one repository; a ticket with no `touches` runs alone in
  its repository.
- A job started by the poller is recorded and shown on the dashboard like any other job.

**Explicitly out of scope:**
- Specs that span several repositories. A spec has one code repository; a work item that touches
  two repositories gives two specs. The Project simply holds tickets of several repositories.
- Local tickets (`specs/<slug>/tickets/T<n>.md`) and `factory/backlog.md`: a ticket must be
  published to the Project to run.
- Picking tickets by assignee or by label.
- Comments on the ticket's issue (result, cost, time). The dashboard holds them.
- Merging or pushing the start branch: a human merges every PR.

## 3. Success Criteria
- A ticket set to Ready, whose dependencies are Done, is picked up within 5 minutes, in its own
  code repository, without a Claude Code session.
- The ticket's Status follows its job until Done, for tickets of different repositories in the
  same Project.

---

# Feature: JidoTa operated from one command

## 1. Description
Today the code factory is driven from a Claude Code session, with `/jidota:code-factory` and the
`factory.py` commands. With this feature, JidoTa has its own `jidota` command, installed as a .NET
tool. It sets JidoTa up, starts and stops it in the background, shows its state, and acts on jobs
without a Claude Code session.

## 2. Scope
**In scope:**
- `jidota` is installed as a .NET tool. It holds the whole of JidoTa: poller, job loop, recording
  and dashboard. It replaces `factory.py`.
- `jidota init` runs first, before any spec factory run:
  - asks which GitHub Project holds the specs and tickets, and which GitHub repository the spec
    factory creates their issues in;
  - adds In Review and Needs human to the Status field of that Project when they are missing;
  - writes the one configuration file of JidoTa: the GitHub Project, the issues repository, the
    poll interval (5 minutes), the parallel-jobs limit (3), the reviewers (security, code), the
    maximum rework rounds (2), the folder of the clones, the PostgreSQL connection;
  - creates the local PostgreSQL Docker container, or reuses it, and creates or updates the tables;
  - checks the prerequisites (`claude` signed in, `gh` with the `project` scope, `az`, `git`,
    Docker) and says what is missing.
- The spec factory publishes to the Project and the repository of this configuration. It stops
  with an error that says to run `jidota init` when the configuration does not exist.
  `~/.claude/spec-factory.json` is no longer read.
- `jidota start` starts JidoTa in the background (poller, job loop, dashboard process) and gives
  the terminal back.
- `jidota stop` stops JidoTa cleanly: no new job or agent run starts, each running `claude -p` run
  finishes, then it stops. A job stopped between two runs carries on at its next step on the next
  `jidota start`.
- On start after a stop, a crash or a reboot, `jidota` resumes every unfinished job at its next
  step, found from the database and the job files. A run cut by a crash is started again once; a
  second failure sends the job to needs-human.
- `jidota status` shows whether JidoTa is running or paused, the running jobs, the free slots, the
  last poll and the dashboard address.
- When a run fails on the subscription quota or an expired `claude` session, JidoTa pauses: no run
  starts and jobs stay at their step. After a quota failure it resumes on its own when the limit resets;
  after an auth failure, `jidota resume` ends the pause once `claude` is signed in again.
- `jidota run <ticket | spec>`, `jidota approve <job>`, `jidota rework <job> <note>` and
  `jidota cancel <job>` act on jobs from the command line, with the rules of the dashboard. Each
  action is recorded with the job, like the dashboard's.
- `jidota clean` removes the worktrees of finished jobs.
- The Python scripts of the interactive skills become subcommands of `jidota`, with the same
  inputs, outputs and exit codes, and their `SKILL.md` calls them:
  - spec factory: `jidota spec fetch` (`fetch_source.py`), `jidota spec graph` (`ticket_graph.py`,
    from the existing `Graph/GraphNet`), `jidota spec publish` (`publish_github.py`);
  - `/jidota:branch-to-pr`: `jidota pr collect | open` (`branch_to_pr.py`);
  - `/jidota:workitems`: `jidota workitems target | check | create` (`workitems.py`).
- Python and PyYAML are no longer prerequisites.

**Explicitly out of scope:**
- Changing what the interactive skills do: only their scripts move to .NET.

## 3. Success Criteria
- On a machine with the prerequisites, JidoTa is set up with `jidota init` and running after
  `jidota start`, with no Claude Code session.
- `jidota stop` never interrupts a running agent run.
- A spec factory run without `jidota init` stops with an error before reading the source.
- The spec factory, `/jidota:branch-to-pr` and `/jidota:workitems` run on a machine with no Python.

---

# Documents to align when this is built

- `README.md`, Workflow: Done is set by `jidota` when the PR is merged, not by the human.
- `Factory/README.md`: merge delivery, `backlog.md`, local tickets, `next`, `board.json` and the
  `python -m http.server` dashboard are gone; the spec factory destination comes from the `jidota`
  configuration, not from `--repo` / `--project`, `published.json` or `~/.claude/spec-factory.json`.
- `Factory/README.md`: the Factory section describes `jidota` and the agents, no longer the
  `/jidota:code-factory` skill; `skills/code-factory/` is removed.
- `Factory/README.md` and `Graph/README.md`: Python prerequisites, the `scripts/` folders and the
  copy of `ticket_graph.py` in the plugin are gone; `Graph/PyGraph` stays only as the prototype.
- Memory of the 2026-10-15 design: SQLite, Linear, "one run per repo", "Done always set by a human"
  and the 90-day retention are superseded by these features.
