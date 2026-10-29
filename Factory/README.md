# Spec factory

MVP of the upstream half of JidoTa: it turns a work item into a spec and child tickets that the
[ticket graph](../Graph/README.md) can schedule. The downstream half, the [code factory](#factory),
turns one of those tickets into tested, reviewed, committed code; it is a second skill of the same
plugin.

It is packaged as the Claude Code plugin `jidota` (this folder). Open Claude Code at the root of the
repository whose code the work item changes, with the plugin loaded for the session:

```powershell
cd D:\Source\Repos\<target-repo>
claude --plugin-dir D:\Source\Repos\jidota\Factory
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

The code factory turns tickets into tested, reviewed code, squash-merged into each ticket's
`start_branch` or proposed as a draft pull request. Several tickets run at once, each in its own git
worktree, up to a limit. A spec is never built as such: given a spec, the factory queues its tickets.
A job is always one ticket, and every job knows its spec.

Run it from the root of the code repository, with the same plugin loaded:

```
/jidota:code-factory specs/ado-886/tickets/T1.md
/jidota:code-factory https://github.com/benkemt/specs/issues/36 --pr
```

The session that runs it becomes the orchestrator: it spawns every agent, drives every running job
at once, and is the only writer of `factory/board.json`. It never writes code, reviews, or decisions
itself. Run one orchestrator session per repository.

### The loop

Reviewers: security, code. Max rework rounds: 2. Delivery: merge. Parallel jobs: 3. All four are set
at the top of [`skills/code-factory/SKILL.md`](skills/code-factory/SKILL.md).

| Step | Who | Output in `factory/jobs/<id>/` | Next |
|---|---|---|---|
| 1. Ticket → job: dependency check, slot and touches check, worktree | `factory.py new` | `spec.md` (job table, dependencies, raw ticket and spec) | build |
| 2. Implement in passes with proof, commit on `factory/<id>` in the job's worktree | `jidota:builder` (opus) | `build.md` | `STATUS: DONE` → review, `BLOCKED` → blocked |
| 3. Review the diff, all reviewers at once | `jidota:security-reviewer`, `jidota:code-reviewer` (opus) | `round-<n>/review-<name>.md` | wait for all; any `CHANGES` → builder again (2 rounds max, then needs-human); all `PASS` → approve |
| 4. Decide | `jidota:approver` (opus) | `decision.md` | `APPROVE` → deliver, `ESCALATE` → needs-human |
| 5a. Delivery `merge`: squash-merge into `start_branch` with the job's commit subject, one merge at a time, then remove the worktree | `factory.py merge` | | done, or needs-human on conflict |
| 5b. Delivery `draft-pr`: push the job branch, open a draft PR into `start_branch` | `factory.py pr` | | pr; done once a human merges the PR |

Every factory commit of a ticket, the squash-merge commit and the PR title use one subject:
`T<n> - <ticket title> (<key>)`, or `(<slug>)` for a local ticket that is not published yet. The
dependency checks match that exact subject in `git log --format=%s <start_branch>`, so `#33` never
matches `#330`, and the T1 of two specs never collide.

### Parallel jobs

| Rule | How |
|---|---|
| One worktree per job | `factory.py new` runs `git worktree add -b factory/<job-id> ../<repo>.worktrees/<job-id> <start_branch>`. The worktree sits next to the repository, so tools started from the repo root never see another job's copy. The builder and the reviewers work only there; the main working tree only receives merges. |
| The whole frontier | `next` starts every ready backlog line (dependencies done, touches free) while a slot is free, and the orchestrator calls it again each time a job leaves the running stages, until nothing runs and nothing is ready. |
| Never two open jobs on the same file | A ticket waits while its `touches` overlap those of a job not yet done (a job at pr, needs-human or blocked still holds its files). A ticket with no `touches` runs alone. In the sample, T4 waits for T3: both touch `installer/Common/Http.ps1`. |
| A limit | Running jobs (spec, build, review, approve) never exceed Parallel jobs. Jobs at pr, needs-human or blocked take no slot. |
| Merges one at a time | `factory/merge.lock` serializes squash-merges into `start_branch`. A job that conflicts with a merge made since it started goes to needs-human with the files; `rework` has the builder merge `start_branch` into its branch (never a rebase) and prove again. |
| A lock on the board | `factory/board.lock` around every write of `board.json` and `backlog.md`: parallel commands lose no update. A command waits up to 30 s; a board lock older than 2 min, or a merge lock older than 10 min, is stale and broken. |

A merge without conflict is not re-tested on the combined `start_branch`: disjoint `touches` keep that
risk low, and the start branch CI stays the safety net. A repository whose tests share a fixed port,
a local database or another machine-wide resource runs with Parallel jobs: 1. The builder never uses
`git stash`: the stash is shared by every worktree of a repository.

### Delivery: merge or draft PR

| | `merge` (default) | `draft-pr` (`--pr`) |
|---|---|---|
| After APPROVE | squash-merge into the local `start_branch`, stage done | push `factory/<job-id>` to `origin`, open a draft PR into `start_branch`, stage pr |
| After ESCALATE | needs-human, nothing pushed | needs-human, and the draft PR is opened too, escalation reasons on top |
| What is pushed | nothing | the job branch only: never `start_branch`, never a force push |
| A dependent ticket starts when | the squash commit is on `start_branch` | the host reports the PR merged (the job then turns done) |

The host comes from `git remote get-url origin`: GitHub (`gh pr create --draft`) or Azure DevOps
Repos (`az repos pr create --draft true`); any other host is an error. The PR description is built
from the job files: ticket and spec, the Proof table and test counts, the review verdicts, and the
decision. A rework after the PR is open adds commits to the same branch and updates the same PR.
Marking the PR ready, approving and completing it stay human. Set the default in the Delivery line
of the SKILL.md; `--pr` or `--merge` after a ticket, a spec or `next` overrides it for that job.

### Commands

| Command | Effect |
|---|---|
| `/jidota:code-factory <ticket>` | Run a ticket (GitHub issue URL, `owner/repo#n`, or `specs/<slug>/tickets/T<n>.md`) through the loop. Exit 4 shows the dependencies not done yet, exit 5 the job it overlaps or the full slots, and stops. |
| `/jidota:code-factory <spec>` | Queue the spec's tickets (`specs/<slug>/spec.md`, or a spec issue) in `backlog.md` in wave order, `[HUMAN]` ones as `[HUMAN]` lines, show the queue, then run `next`. |
| `/jidota:code-factory next` | Start every ready agent ticket of `backlog.md` up to the limit, drive them all through the loop, refill each freed slot, and stop when nothing runs and nothing is ready. Each line taken is checked with its job id; the report shows what each remaining line waits for. |
| `/jidota:code-factory approve <job-id>` | Accept a needs-human job as it is: merge it into its start branch, or, in draft-pr delivery, push it and open (or update) its draft PR. |
| `/jidota:code-factory rework <job-id> <note>` | For a needs-human, blocked or pr job: write the note to a new `round-<n>/review-human.md` (`VERDICT: CHANGES`), resume the builder on it, then run a full review round. Resets the rework count. After a merge conflict, the builder first merges `start_branch` into its branch. |
| `/jidota:code-factory clean` | Mark the jobs whose PR was merged as done, and remove the worktrees of done jobs (never one with uncommitted changes). |
| `/jidota:code-factory` | Create `factory/` if needed, show the board summary and the accepted forms. |

`--pr` or `--merge` after a ticket, a spec or `next` sets the delivery of the jobs it creates. In
draft-pr delivery, `next` stops at tickets that depend on an open PR: they start on a later `next`,
once a human has merged it.

A dependency is done when a job of that ticket is `done` on the board, or its commit subject is on
`start_branch` (merged by hand), or its job is at stage pr and the host reports the PR merged (a
host rewrites the squash message of a PR, so the subject alone cannot find it). A `[HUMAN]` dependency is done when its issue is closed, or, for a
local ticket, when its `backlog.md` line is checked: the person who does it checks the line.

### Dashboard

```powershell
cd factory
python -m http.server 8765
```

Then open http://localhost:8765/dashboard.html. It polls `board.json` every 2 s: jobs are cards
moving across spec · build · review · approve · pr · done, the header shows the running jobs against
the limit (`running 2 / 3`), needs-human and blocked jobs stand out
with their reason, each review round is a row of reviewer chips, a card with a draft PR links to it,
and a row of spec chips filters the board to one spec (kept in the URL hash). Click a card to read
its markdown files and see its worktree.

### Files

| Path | Role |
|---|---|
| [`skills/code-factory/SKILL.md`](skills/code-factory/SKILL.md) | Orchestrator instructions, with the loop settings |
| [`skills/code-factory/scripts/factory.py`](skills/code-factory/scripts/factory.py) | Board, locks, worktrees, backlog, job folders, rounds, merge, draft PR, clean. Stdlib only, JSON on stdout. Exit codes: 0 ok, 1 error, 2 [HUMAN] ticket, 3 open job, 4 dependency not done, 5 busy (no free slot, or touches overlap an open job) |
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
  board.lock, merge.lock  present only while a command writes the board, or a merge runs
  dashboard.html
  backlog.md              queue for `next`, filled by hand or from a spec
  jobs/<id>/              spec.md, build.md, round-<n>/review-<name>.md, decision.md
```

The worktrees live next to the repository, in `../<repo>.worktrees/<job-id>/`. A job keeps its
worktree until it is done (merge removes it; `clean` removes those of jobs whose PR was merged).

### Prerequisites

- A clean main working tree (no uncommitted change to tracked files) when a merge runs: merges
  happen there, one at a time. Jobs themselves work in their own worktrees.
- Write access to the parent folder of the repository, for `../<repo>.worktrees/`.
- The build and test commands of the repository, as the tickets' How to check use them.
- For GitHub tickets and specs: `gh` authenticated with read access to the spec repository.
- For draft-pr delivery: push rights on `origin`, and `gh` (GitHub) or `az` with the `azure-devops`
  extension (Azure DevOps Repos), logged in with the right to create pull requests.
- Python 3.9+ (stdlib only).

### What it does not do yet

- Push `start_branch`, mark a PR ready, approve or complete it, or comment on the ticket: those stay human.
- Link the PR to the ticket or to an Azure DevOps work item.
- Re-test a merge on the combined `start_branch`: each job is proven on its own branch only.
- Resolve a merge conflict by itself: a conflicting job waits for a human `rework`.
- Resume the agents of an ended session: its running jobs go to needs-human, and `rework` restarts
  them with a fresh builder.
- Count the slots across several orchestrator sessions on one repository.
- Close the GitHub issue of a merged ticket, or read `[HUMAN]` status from anything but the issue
  state or the backlog line.
- Read Linear or Azure DevOps tickets: the tickets come from GitHub or from local files.

## Branch to PR

The `/jidota:branch-to-pr` skill opens a draft pull request from a source branch into a destination
branch, with a description in a fixed model: What, How, Proof, Not in this PR.

```
/jidota:branch-to-pr feature/iis-headers dev
/jidota:branch-to-pr factory/003-t1-remove-server-header dev --title "Remove the Server header"
```

| Step | Who |
|---|---|
| 1. Commits of the source missing from `origin/<destination>`, push needed or not, conflicts, open PR of the same branches | `branch_to_pr.py collect` |
| 2. Tickets of those commits: subject `T<n> - <title> (<key>)` (a round or a host squash of one too), found on the factory board, then in `specs/*/tickets/`, then as an issue of the `repo` of `~/.claude/spec-factory.json`; their spec, the spec's `(scope)` ADO work items, the job files | `branch_to_pr.py collect` |
| 3. Read the diff, the tickets and `build.md`, write the description | the session |
| 4. **The user approves** the title and the description | the session |
| 5. Push the source branch, open the draft PR (or update the open one), link the ADO scope work items (Azure DevOps host) | `branch_to_pr.py open` |

Without a ticket, only what the diff shows is written: no acceptance criteria, no test counts, no
"Not in this PR". The skill never runs the build or the tests: every number comes from a recorded
run (`build.md` of a factory job). It pushes the source branch only, never with force, never the
destination, and never marks the PR ready. Its work files (`context.json`, copies of the tickets and
specs, `body.md`) live in `.git/branch-to-pr/<source>/`, out of the working tree.

| Path | Role |
|---|---|
| [`skills/branch-to-pr/SKILL.md`](skills/branch-to-pr/SKILL.md) | The description model and where each part comes from |
| [`skills/branch-to-pr/scripts/branch_to_pr.py`](skills/branch-to-pr/scripts/branch_to_pr.py) | `collect` and `open`. Imports `factory.py` of the code factory for git, tickets, specs and the GitHub / Azure DevOps host. Exit codes: 0 ok, 1 error, 2 nothing to propose |

Prerequisites: those of the draft-pr delivery of the code factory (push rights on `origin`, `gh` or
`az` with the `azure-devops` extension), and `gh` read access to the spec repository for GitHub tickets.
