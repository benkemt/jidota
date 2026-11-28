# 18 — Agent launcher (`claude -p` per run)

**Depends on:** 08, 15, 16, 17
**Reference:** ARCHITECTURE.md §2 (One agent run, one process, one record), §4 (Agents/, One agent
run), §7.1 (Retry), §8.3 (Run duration, Run budget), §11 (Traps), §12 (Invariants 3, 5, 13)

## Goal

Start one agent run as its own `claude -p` process with the instructions built by `jidota`, stream
its output to the recorder, and end it within its time and budget.

## Job to do

1. **Before the process starts**: record the starting commit (`rev-parse HEAD`, clean or dirty,
   ticket 08), then insert the `agent_runs` row with status `running` (Invariant 3).
2. **System prompt** written to `<job folder>/system-<agent>.md`: a header, then the body of
   `plugin/agents/<agent>.md` after its front matter. Header content: the code repository, branch
   `factory/<job-id>`, worktree, job folder, and "you run unattended: no one can answer a question
   during the run". The agent files are never edited.
3. **Front matter** of the agent file: `model` → `--model`, `tools` → `--tools`.
4. **Command**, through the process runner, working directory = worktree:

   ```
   claude -p "<task>"
     --append-system-prompt-file <job folder>/system-<agent>.md
     --model <model> --tools <tools>
     --settings <data>/jidota/settings/<host>/<repo>.json
     --setting-sources user --strict-mcp-config
     --permission-prompts none
     --session-id <uuid chosen by jidota>        (rework: --resume <builder session id>)
     --add-dir <job folder>
     --output-format stream-json --verbose
     --max-budget-usd <run budget>
   ```

5. **Tasks** (paths only, never ticket text — Invariant 5):

   | Agent | Task |
   |---|---|
   | builder, build | `Mode: build. Job folder: <job folder>. Worktree: <worktree>` |
   | builder, rework | `Mode: rework. Job folder: <job folder>. Round folder: <job folder>/round-<n>/. Worktree: <worktree>` |
   | reviewer `<name>` | `Job folder: <job folder>. Round folder: <job folder>/round-<n>/. Worktree: <worktree>` |
   | approver | `Job folder: <job folder>. Worktree: <worktree>` |

6. **Limits**: kill the tree after the run duration (60 min) → `timeout`; cancellation → `cancelled`;
   exit without `result` → `crashed`. The `claude` executable path is an option (default `claude`
   on `PATH`) so tests use FakeClaude.

Traps: `--permission-prompts none` (otherwise Manual mode may wait for a permission host);
`--setting-sources user --strict-mcp-config` (otherwise the repository's hooks and `.mcp.json` run
with no trust dialog); not `--bare` (it skips `CLAUDE.md` and `CLAUDE_CODE_OAUTH_TOKEN`); on
`--resume` the first launch's system prompt is sent again; SIGTERM gives exit 143 and no `result`.

## Automated tests

`Category=Integration` with FakeClaude and Testcontainers:

- The recorded argv equals the command above, for each agent and for a rework (`--resume`).
- `system-builder.md` = header + body of `builder.md` without its front matter.
- The `agent_runs` row exists before FakeClaude starts (FakeClaude scenario checks the row through
  a test hook) and holds the starting commit.
- `hang` scenario with a 2-second duration → `timeout`, no process left; cancel → `cancelled`.
- No task argument contains text of the ticket fixture.

## How to verify

`dotnet test --filter FullyQualifiedName~AgentLauncher`.

## Acceptance criteria

- [ ] The argv has every flag of the command, and never `--dangerously-skip-permissions`
- [ ] The run row and starting commit exist before the process starts
- [ ] Timeout and cancel kill the tree and set `timeout` / `cancelled`
- [ ] Tasks hold paths only
- [ ] The system prompt file is kept in the job folder for every run
