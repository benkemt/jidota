# Spec factory

MVP of the upstream half of JidoTa: it turns a work item into a spec and child tickets that the
[ticket graph](../Graph/README.md) can schedule. The downstream half, the [code factory](#factory),
turns one of those tickets into tested, reviewed, committed code; it is a second skill of the same
plugin.

It is packaged as the Claude Code plugin `jidota` (this folder). Open Claude Code at the root of the
repository whose code the work item changes, with the plugin loaded for the session:

```powershell
cd D:\Source\Repos\<target-repo>
claude --plugin-dir D:\Source\Repos\jidota\SpecFactory
```

Then:

```
/jidota:spec-factory ado#886
/jidota:spec-factory https://github.com/<owner>/<repo>/issues/12
```

The agents read the code of that repository, wherever it is hosted (Azure DevOps Repos or GitHub).

## Where the spec and tickets go

They are always GitHub issues: the spec is one issue, each ticket is a sub-issue of it. A GitHub
Project cannot hold issues by itself, so the issues live in a GitHub repository and are then added
to the project. The destination is the first one found:

1. `--repo owner/repo` and `--project owner/number` after the source:
   `/jidota:spec-factory ado#886 --repo benkemt/specs --project benkemt/2`
2. The repository and project an earlier run of the same source already published to (`published.json`).
3. `~/.claude/spec-factory.json`, for a destination that does not change:

   ```json
   { "repo": "benkemt/specs", "project": "benkemt/2" }
   ```

4. The GitHub remote of the current folder, with no project.

The run shows the destination before reading the source and asks before creating anything.
Each spec and ticket carries `code_repo` (the code repository's remote URL) and `base_commit`, so
an agent reading the issue knows which repository and commit its `path:line` references point to.

Adding issues to a project needs the `project` scope on the GitHub CLI token, once:
`gh auth refresh -s project`.

The working files (`specs/<slug>/`) are written in the code repository. To keep them out of its
commits without touching its `.gitignore`, add `specs/` to `.git/info/exclude`.

## The loop

The `/jidota:spec-factory` skill turns the Claude Code session that runs it into the orchestrator. It is
the only part that talks to the user; two agents do the reading and the writing.

| Step | Who | Output in `specs/<slug>/` |
|---|---|---|
| 1. Read the item and its direct children in state New (ADO) or open (GitHub) | `fetch_source.py` | `source.md` |
| 2. Read the repository, sort the open choices, draft at most five questions | `jidota:spec-writer` (opus) | `research.md` |
| 3. Ask the questions in one round | orchestrator | `answers.md` |
| 4. Write the spec, run its readiness check | `jidota:spec-writer` (opus) | `spec.md` |
| 5. **The user approves the spec** or sends remarks back | orchestrator | |
| 6. Cut the spec into tickets, map each AC to a ticket | `jidota:ticket-writer` (opus) | `tickets/T<n>.md`, `plan.md` |
| 7. Check the graph (`ticket_graph.py`) and AC coverage | orchestrator | |
| 8. **The user approves publication**: spec issue + one sub-issue per ticket | `publish_github.py` | `published.json` |

`slug` is `ado-<id>` or `gh-<number>`. A second run on the same source resumes at the first missing
file; a published source is not published twice.

## Files

| Path | Role |
|---|---|
| [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) | Plugin manifest (`jidota`) |
| [`skills/spec-factory/SKILL.md`](skills/spec-factory/SKILL.md) | Orchestrator instructions |
| [`agents/spec-writer.md`](agents/spec-writer.md) | What a spec is, how to write it |
| [`agents/ticket-writer.md`](agents/ticket-writer.md) | What a ticket is, how to cut a spec |
| [`skills/spec-factory/scripts/fetch_source.py`](skills/spec-factory/scripts/fetch_source.py) | ADO (`az`) / GitHub (`gh`) → `source.md` |
| [`skills/spec-factory/scripts/publish_github.py`](skills/spec-factory/scripts/publish_github.py) | Spec + tickets → GitHub issue and sub-issues |
| [`skills/spec-factory/scripts/ticket_graph.py`](skills/spec-factory/scripts/ticket_graph.py) | Copy of [`Graph/PyGraph/ticket_graph.py`](../Graph/PyGraph/ticket_graph.py), so the plugin works outside this repository. Copy it again after changing the original |
| [`SPEC_FACTORY_BUILD_PROMPT.md`](SPEC_FACTORY_BUILD_PROMPT.md) | The request this MVP was built from |

Ticket files keep the frame of the ticket graph (`# T<n> — title`, first yaml block with `id`,
`depends_on`, `start_branch`, `touches`), so the same folder is both the publication input and the
scheduler input.

## Prerequisites

- `gh` authenticated with issue write access on the destination repository, plus the `project`
  scope when a project is set.
- For ADO: `az` with the `azure-devops` extension, logged in. `ado#<id>` uses
  `az devops configure --defaults`; a full work item URL sets the organization itself.
- Python 3.9+; PyYAML for the graph check.

## What it does not do yet

- Publish to Linear or to Azure DevOps: specs and tickets go to GitHub only.
- Turn `depends_on` into GitHub "blocked by" relations: dependencies live in each ticket's yaml.
- Write anything on the source work item: the link source → spec exists only in the spec's `sources`.
- Read grandchildren: an Epic gives its Features, not their Stories.
- Review the spec with a second agent before the human does.

## Factory

The code factory takes **one ticket** and turns it into tested, reviewed code, squash-merged into the
ticket's `start_branch`. A spec is never built as such: given a spec, the factory queues its tickets.
A job is always one ticket, and every job knows its spec.

Run it from the root of the code repository, with the same plugin loaded:

```
/jidota:code-factory specs/ado-886/tickets/T1.md
/jidota:code-factory https://github.com/benkemt/specs/issues/36
```

The session that runs it becomes the orchestrator: it spawns every agent and is the only writer of
`factory/board.json`. It never writes code, reviews, or decisions itself.

### The loop

Reviewers: security, code. Max rework rounds: 2. Both are set at the top of
[`skills/code-factory/SKILL.md`](skills/code-factory/SKILL.md).

| Step | Who | Output in `factory/jobs/<id>/` | Next |
|---|---|---|---|
| 1. Ticket → job, dependency check | `factory.py new` | `spec.md` (job table, dependencies, raw ticket and spec) | build |
| 2. Implement in passes with proof, commit on `factory/<id>` | `jidota:builder` (opus) | `build.md` | `STATUS: DONE` → review, `BLOCKED` → blocked |
| 3. Review the diff, all reviewers at once | `jidota:security-reviewer`, `jidota:code-reviewer` (opus) | `round-<n>/review-<name>.md` | wait for all; any `CHANGES` → builder again (2 rounds max, then needs-human); all `PASS` → approve |
| 4. Decide | `jidota:approver` (opus) | `decision.md` | `APPROVE` → merge, `ESCALATE` → needs-human |
| 5. Squash-merge into `start_branch` with the job's commit subject | `factory.py merge` | | done, or needs-human on conflict |

Every factory commit of a ticket, and the squash-merge commit, use one subject:
`T<n> - <ticket title> (<key>)`, or `(<slug>)` for a local ticket that is not published yet. The
dependency checks match that exact subject in `git log --format=%s <start_branch>`, so `#33` never
matches `#330`, and the T1 of two specs never collide.

### Commands

| Command | Effect |
|---|---|
| `/jidota:code-factory <ticket>` | Run a ticket (GitHub issue URL, `owner/repo#n`, or `specs/<slug>/tickets/T<n>.md`) through the loop. Exit 4 shows the dependencies not done yet and stops. |
| `/jidota:code-factory <spec>` | Queue the spec's tickets (`specs/<slug>/spec.md`, or a spec issue) in `backlog.md` in wave order, `[HUMAN]` ones as `[HUMAN]` lines, show the queue, then run `next` once. |
| `/jidota:code-factory next` | Run the first unchecked agent ticket of `backlog.md` whose dependencies are done, and check its line with the job id. When none is ready, show what each line waits for. |
| `/jidota:code-factory approve <job-id>` | Merge a needs-human job into its start branch as it is. |
| `/jidota:code-factory rework <job-id> <note>` | Write the note to a new `round-<n>/review-human.md` (`VERDICT: CHANGES`), resume the builder on it, then run a full review round. Resets the rework count. |
| `/jidota:code-factory` | Create `factory/` if needed, show the board summary and the accepted forms. |

A dependency is done when a job of that ticket is `done` on the board, or its commit subject is on
`start_branch` (merged by hand). A `[HUMAN]` dependency is done when its issue is closed, or, for a
local ticket, when its `backlog.md` line is checked: the person who does it checks the line.

### Dashboard

```powershell
cd factory
python -m http.server 8765
```

Then open http://localhost:8765/dashboard.html. It polls `board.json` every 2 s: jobs are cards
moving across spec · build · review · approve · done, needs-human and blocked jobs stand out with
their reason, each review round is a row of reviewer chips, and a row of spec chips filters the board
to one spec (kept in the URL hash). Click a card to read its markdown files.

### Files

| Path | Role |
|---|---|
| [`skills/code-factory/SKILL.md`](skills/code-factory/SKILL.md) | Orchestrator instructions, with the loop settings |
| [`skills/code-factory/scripts/factory.py`](skills/code-factory/scripts/factory.py) | Board, backlog, job folders, rounds, merge. Stdlib only, JSON on stdout. Exit codes: 0 ok, 1 error, 2 [HUMAN] ticket, 3 open job, 4 dependency not done |
| [`skills/code-factory/dashboard.html`](skills/code-factory/dashboard.html) | Self-contained board, copied into `factory/` by `factory.py init` |
| [`agents/builder.md`](agents/builder.md) | Passes 0–5: frame, baseline, red tests, implementation, counter-checks, commit and report |
| [`agents/security-reviewer.md`](agents/security-reviewer.md) | Injection, secrets, authz, unsafe input, risky dependencies, in the diff only |
| [`agents/code-reviewer.md`](agents/code-reviewer.md) | Correctness against Contracts and AC, test quality, scope; re-runs How to check |
| [`agents/approver.md`](agents/approver.md) | APPROVE or ESCALATE from the job's files and the diff stat |
| [`FACTORY_BUILD_PROMPT.md`](FACTORY_BUILD_PROMPT.md) | The request the code factory was built from |

In the code repository, `factory/` is excluded through `.git/info/exclude`:

```
factory/
  board.json              durable state, drives the dashboard
  dashboard.html
  backlog.md              queue for `next`, filled by hand or from a spec
  jobs/<id>/              spec.md, build.md, round-<n>/review-<name>.md, decision.md
```

### Prerequisites

- A clean working tree (no uncommitted change to tracked files) before a job starts: the builder
  works in the main working tree, on `factory/<job-id>`.
- The build and test commands of the repository, as the tickets' How to check use them.
- For GitHub tickets and specs: `gh` authenticated with read access to the spec repository.
- Python 3.9+ (stdlib only).

### What it does not do yet

- Push, open a PR, or comment on the ticket: merging stays local to `start_branch`, pushing stays human.
- Run several jobs at once: one job at a time, in the main working tree (no worktrees).
- Run a whole backlog in one call: `next` runs one ticket per invocation.
- Close the GitHub issue of a merged ticket, or read `[HUMAN]` status from anything but the issue
  state or the backlog line.
- Read Linear or Azure DevOps tickets: the tickets come from GitHub or from local files.
