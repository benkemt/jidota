# 03 — Logging setup and log rules

**Depends on:** 01
**Reference:** ARCHITECTURE.md §2.2 (Logging), §10 (Observability), §10.1 (Logs), §10.2 (Tracing)

## Goal

Configure `Microsoft.Extensions.Logging` with Serilog once, with the scopes and the rules every
module follows, so logs can be filtered by job and run and never carry secrets or agent output.

## Job to do

1. Serilog, compact JSON formatter, file sink, one file per day in `<data>/jidota/logs/` (the
   `<data>` folder comes from ticket 04; until then take the folder as a parameter).
2. A logging scope helper that adds `job_id`, and for a run `run_id` and `session_id`, to every
   line written inside it.
3. Levels, as §10.1 states them:

   | Level | What |
   |---|---|
   | `Information` | poll done (tickets seen, started), each transition, each human action, each Status write, pause and resume |
   | `Warning` | retried CLI call, Status restored after a manual change, ticket ignored and why |
   | `Error` | failed CLI call after retries, run ended other than `finished` |
   | `Debug` | the CLI commands run (arguments only, never their output) |

4. Never logged: secrets, the output of agent runs (it is in `run_lines`), ticket bodies. Provide
   one helper to log an untrusted value truncated (§9.2 "the value is logged truncated").
5. No tracing system (§10.2 is N/A): the job id, run id and session id are the correlation.

> Log file retention is **Not decided** (§8.3). Keep every daily file; leave the retention as a
> setting with no limit, so it can be set later without code change.

## Automated tests

- `Category=Unit`: a log line written inside a job and run scope holds `job_id`, `run_id`,
  `session_id` as JSON properties (sink to a temporary folder).
- `Category=Unit`: the truncation helper cuts a 10 000-character value to the configured length.
- `Category=Unit`: a `Debug` line for a command holds its arguments and not its stdout.

## How to verify

Run any command of the tool, then open the file of the day in `<data>/jidota/logs/`: each line is
one JSON object.

## Acceptance criteria

- [ ] One JSON file per day is written in the logs folder
- [ ] Lines inside a job scope carry `job_id`; inside a run scope also `run_id` and `session_id`
- [ ] No helper writes a process's stdout to the log
- [ ] Untrusted values are logged truncated
