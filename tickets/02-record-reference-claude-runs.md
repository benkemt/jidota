# 02 — Reference `claude -p` runs recorded as test fixtures

**Depends on:** 01
**Reference:** ARCHITECTURE.md §4 (One agent run), §7.1 (Retry), §11 (Traps already met, To verify
in the first spike)

## Goal

Run the real `claude -p` once on the cases the design relies on, answer the open questions of §11,
and keep each `stream-json` output as a fixture. The fake `claude` (ticket 16) replays these files,
so every later test runs in a pipeline without tokens.

## Job to do

Run, in a throwaway git repository, with the flags of §4:

```
claude -p "<task>" --append-system-prompt-file <file> --model <model> --tools Read,Grep,Glob,Bash,Write,Edit
  --settings <file> --setting-sources user --strict-mcp-config --permission-prompts none
  --session-id <uuid> --add-dir <folder> --output-format stream-json --verbose --max-budget-usd <n>
```

Record each run's stdout to `tests/Jidota.Tests/Fixtures/stream-json/<case>.jsonl`, after
replacing any token, user name or path of the machine by a placeholder:

| Case | What it must show |
|---|---|
| `finished.jsonl` | `system`/`init`, `assistant` with `tool_use`, `user` with `tool_result`, final `result` with `usage`, `total_cost_usd`, `num_turns`, `duration_ms`, `duration_api_ms` |
| `tool-error.jsonl` | a `tool_result` with `is_error: true` |
| `permission-denied.jsonl` | a Bash command not allowed by `--settings`: a `system`/`permission_denied` message and `permission_denials` in `result` (`tool_name`, `tool_use_id`, `tool_input`) |
| `resume.jsonl` | a second run with `--resume <session id>` of `finished.jsonl` |
| `budget.jsonl` | a run stopped by `--max-budget-usd` |
| `rate-limit.jsonl` | a `rate_limit_event` line, if one is seen (`allowed_warning` at least) |

Answer in `tests/Jidota.Tests/Fixtures/stream-json/README.md`:

1. The unit of `rate_limit_info.resetsAt` (seconds or milliseconds since the epoch). The
   reference documents `status` (`allowed` | `allowed_warning` | `rejected`), `resetsAt`,
   `utilization`; nothing undocumented is relied on.
2. Whether `total_cost_usd` of the `--resume` run counts from that run or from the start of the
   session. The sum of cost per job depends on it.
3. That `--append-system-prompt-file` keeps the repository's `CLAUDE.md`, and that on `--resume`
   the system prompt of the first launch is sent again (`--system-prompt-snapshot`).

Traps to keep in mind while recording: without `--permission-prompts none`, `-p` (v2.1.302+)
starts in Manual mode and may wait for a permission host; without `--setting-sources user
--strict-mcp-config`, the repository's hooks and `.mcp.json` servers run with no trust dialog.

## Automated tests

- `Category=Unit`: every fixture file parses line by line as JSON, and holds no string matching
  the masking patterns of ticket 14 (no token left in a committed fixture).

## How to verify

Read the fixture README: each of the three questions has an answer with the fixture that shows it.

## Acceptance criteria

- [ ] The six fixtures exist (`rate-limit.jsonl` may be missing, with the reason in the README)
- [ ] `permission-denied.jsonl` holds both the `system`/`permission_denied` message and a
      non-empty `permission_denials` in `result`
- [ ] The README answers the three questions, citing the fixture lines
- [ ] No fixture contains a token, a user name or a home path of the recording machine
