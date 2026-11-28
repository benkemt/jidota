# 35 — Dashboard: Run replay and run comparison

**Depends on:** 15, 33
**Reference:** ARCHITECTURE.md §5 (Tool call, Raw line), §9.2 (HTML in the dashboard), §10
(`agent_runs`, `tool_calls`, `run_lines`); feature "Cost and time visible per work item" (Run view,
comparisons)

## Goal

Read one agent run back step by step, and compare runs, to improve the agents' prompts.

## Job to do

1. **Replay** of one run, in order: each tool call with its input and its result, success or
   failure, and its time; the assistant text between them; the run header (agent, model, round,
   session, starting commit, end status, totals). Built from `tool_calls`, with `run_lines` as the
   source of truth for the order and for lines not interpreted.
2. Show the assembled system prompt used by the run (`system-<agent>.md` of the job folder).
3. **Comparison** of runs, chosen by agent (for example every builder run of a month): tools called
   (count per tool), turns, failures (failed tool calls, end statuses), duration and cost.
4. Raw output and tool inputs are shown as text, never as HTML (§9.2). They are already masked
   (ticket 14).

## Automated tests

- `Category=Integration` (Testcontainers): recording `finished.jsonl` (ticket 02) then reading the
  replay gives the tool calls in the fixture's order, with inputs and results.
- `Category=Integration`: `tool-error.jsonl` shows the failed call as failure.
- `Category=Integration`: comparing three builder runs gives per-tool counts, turns and failures
  equal to the fixtures.
- `Category=Unit` (bUnit, fake run service):
  - the replay renders the steps in order; expanding a step shows its full input and result;
  - a failed tool call is rendered as a failure;
  - the system prompt panel shows the run's `system-<agent>.md`;
  - selecting three runs in the comparison renders one column per run with tools, turns, failures;
  - a tool result holding `<img src=x onerror=alert(1)>` is rendered as text.
- `Category=Integration` (`WebApplicationFactory`): the run page without the cookie → 401.

## How to verify

Open a finished job, open its builder run, scroll the replay: every tool call of the run is there
in order (feature success criterion: a run can be read back step by step from the database).

## Acceptance criteria

- [ ] A run is replayed in order with every tool call, input and result
- [ ] The system prompt of the run is shown
- [ ] Runs can be compared by tools, turns and failures
- [ ] No run content is rendered as HTML
