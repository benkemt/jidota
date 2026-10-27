# Spec factory

MVP of the upstream half of JidoTa: it turns a work item into a spec and child tickets that the
[ticket graph](../Graph/README.md) can schedule.

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
| [`BUILD_PROMPT.md`](BUILD_PROMPT.md) | The request this MVP was built from |

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
