# 42 — Interactive skills call `jidota`; Python and the code-factory skill removed

**Depends on:** 36, 37, 38, 39, 40, 41
**Reference:** ARCHITECTURE.md §1 (no Python is needed), §2.1 (Factory/ packaged with the tool);
features (decisions: no Python left, `/jidota:code-factory` removed, interactive skills stay),
"JidoTa operated from one command"

## Goal

The plugin keeps its interactive skills and its agents, with no Python script left, and the code
factory skill gone now that `jidota` is the orchestrator.

## Job to do

1. In each `SKILL.md`, replace the script calls by the subcommands, keeping the arguments and the
   routing on exit codes:

   | Skill | Before | After |
   |---|---|---|
   | `skills/spec-factory/SKILL.md` | `python "${CLAUDE_SKILL_DIR}/scripts/fetch_source.py" "<source>"` | `jidota spec fetch "<source>"` |
   | | `python …/ticket_graph.py specs/<slug>/tickets` | `jidota spec graph specs/<slug>/tickets` |
   | | `python …/publish_github.py --target`, `specs/<slug> --dry-run`, `specs/<slug>` | `jidota spec publish …` (no `--repo` / `--project`: ticket 38) |
   | `skills/branch-to-pr/SKILL.md` | `python "${CLAUDE_SKILL_DIR}/scripts/branch_to_pr.py"` | `jidota pr` |
   | `skills/workitems/SKILL.md` | `python "${CLAUDE_SKILL_DIR}/scripts/workitems.py"` | `jidota workitems` |

2. In `skills/spec-factory/SKILL.md`, the destination text (`--repo`, `--project`,
   `published.json`, `~/.claude/spec-factory.json`) says the destination comes from the jidota
   configuration and that `jidota init` must have run.
3. Remove `skills/code-factory/` (its `SKILL.md`, `dashboard.html`, `scripts/factory.py`) and every
   `scripts/` folder of the plugin, including the copy of `ticket_graph.py`. Keep
   `Factory/agents/` unchanged.
4. Remove the code-factory skill from `.claude-plugin/plugin.json` if it is listed there.
5. Before removing a script, check that its golden files exist (tickets 36–41).

## Automated tests

- `Category=Unit`: no file under `Factory/` matches `python ` or `\.py` (a test scanning the
  plugin folder).
- `Category=Unit`: `Factory/skills/code-factory/` does not exist; `Factory/agents/` holds the six
  agent files.
- `Category=Unit`: each `jidota …` command written in a `SKILL.md` parses with the CLI of
  ticket 32 and the ports (`--help` of the parsed command succeeds).

## How to verify

On a machine with no Python, run `/jidota:spec-factory` on a test work item up to the dry-run
publication, and `/jidota:workitems` up to `check` (feature success criterion: the skills run with
no Python).

## Acceptance criteria

- [ ] Every script call of the three skills is a `jidota` subcommand
- [ ] No Python file is left in the plugin
- [ ] The code-factory skill is removed; the agents are unchanged
- [ ] The spec factory states that the destination comes from `jidota init`
