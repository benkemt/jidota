# 15 — `stream-json` reader and run recorder

**Depends on:** 02, 11, 14
**Reference:** ARCHITECTURE.md §4 (Recording/), §5 (Agent run, Tool call, Raw line), §7.1 (Retry:
quota, permission denied), §11 (Traps); feature "Code factory runs unattended and records every
agent run"

## Goal

Read the stdout of a `claude -p --output-format stream-json --verbose` run line by line, store each
line masked as it arrives, extract the tool calls, and close the run with its totals and end status.

## Job to do

1. For each line, in order: mask (ticket 14), write to `run_lines` right away (a crash keeps all
   that was received, §5), then interpret by `type`:

   | Line | What is taken |
   |---|---|
   | `system` / `init` | session id, model |
   | `assistant` | `tool_use` blocks (id, name, input) open a tool call; per-turn `usage` when present |
   | `user` | `tool_result` blocks close the tool call of the same `tool_use_id` (result, `is_error`) |
   | `system` / `permission_denied` | the denied tool (best-effort; `result` is authoritative) |
   | `rate_limit_event` | `rate_limit_info.status` (`allowed`, `allowed_warning`, `rejected`), `resetsAt`, `utilization` |
   | `result` | `usage` (input, output, cache-creation, cache-read), `total_cost_usd`, `num_turns`, `duration_ms`, `duration_api_ms`, `is_error`, `subtype`, `permission_denials` |
   | anything else | stored, not interpreted |

2. **Find `result` by its `type`, not by position.** A line that is not JSON is stored as is.
3. Tool calls get their start and end time from the arrival of the two lines.
4. End status, from what was read (the launcher of ticket 18 sets `timeout`, `cancelled`,
   `crashed` itself):
   - `permission_denials` not empty → `permission_denied`;
   - a `rate_limit_event` with `rejected` → `quota` (keep `resetsAt` for ticket 28);
   - `result` stopped by the budget (the `subtype` shown in `Fixtures/stream-json/budget.jsonl`) → `budget`;
   - an expired `claude` session → `auth` (classify from the fixture recorded in ticket 02, or a
     recorded sample);
   - otherwise `finished`.
5. **A run with no `result`** keeps the tokens summed from the per-turn usage received, and no cost.
6. Totals stored are exactly the values of `result` (feature success criterion).

## Automated tests

`Category=Integration` (Testcontainers) feeding the fixtures of ticket 02:

- `finished.jsonl`: one `run_lines` row per line; tool calls paired; totals equal the `result`.
- `tool-error.jsonl`: the failed tool call is stored as failure.
- `permission-denied.jsonl` → `permission_denied` with the tool name and input.
- `budget.jsonl` → `budget`; `rate-limit.jsonl` → warning or `quota` with `resetsAt`.
- `finished.jsonl` cut before its `result` line → no cost, tokens from the turns received.
- A fixture with a secret injected in a tool result → `***` in `run_lines` and `tool_calls`.

## How to verify

`dotnet test --filter FullyQualifiedName~Recorder`; then read back one run with SQL in order.

## Acceptance criteria

- [ ] Every line is stored masked, in order, as it arrives
- [ ] Stored totals of a finished run equal its `result` values
- [ ] `result` is found by type even if other lines follow it
- [ ] Each end status of the list is derived from its fixture
- [ ] A run without `result` keeps partial tokens and no cost
