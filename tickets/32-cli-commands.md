# 32 — CLI commands

**Depends on:** 13, 30, 31
**Reference:** ARCHITECTURE.md §6 (Commands, Errors), §9.1 (runs in the background), §11 (To verify:
Linux detach); feature "JidoTa operated from one command"

## Goal

The `jidota` commands that start, stop and drive the running instance from a terminal.

## Job to do

| Command | Needs a running instance | Effect |
|---|---|---|
| `jidota start` | no | starts the same executable detached with the internal `serve` command, writes the token, gives the terminal back |
| `jidota stop` | yes | `POST /api/stop`: drain, then exit |
| `jidota status` | no | running or not, paused or not, running jobs, free slots, last poll, dashboard URL (with the token) |
| `jidota resume` | yes | ends a quota or auth pause |
| `jidota run <ticket \| spec>` | yes | `POST /api/jobs` |
| `jidota approve <job>` | yes | approve |
| `jidota rework <job> <note>` | yes | rework |
| `jidota cancel <job>` | yes | cancel |
| `jidota clean` | no | removes the worktrees of done and cancelled jobs, never one with uncommitted changes, and reports those kept with the reason |

Exit codes (0–5 keep their `factory.py` meaning):

| Exit | Meaning |
|---|---|
| 0 | ok |
| 1 | error (message on stderr), including 401 and 404 |
| 2 | `[HUMAN]` ticket |
| 3 | open job, wrong stage, or a run is active |
| 4 | not eligible: not Ready, or a dependency not Done |
| 5 | busy: touches overlap or no free slot |
| 6 | no running instance |

> **To verify (§11):** on Linux, the instance started by `jidota start` must be detached from the
> terminal (its own session, as `setsid` gives) and survive the terminal being closed. On Windows,
> start it with no console window.

## Automated tests

- `Category=Unit`: each API response maps to its exit code.
- `Category=Unit`: a command that needs an instance, with none running, exits 6 with the message.
- `Category=Integration`: `jidota clean` removes a clean worktree of a done job and keeps a dirty one
  with its reason (bare git origin).
- `Category=Integration` (Linux): `jidota start` from a child shell that then exits; the instance
  still answers `GET /api/status`.

## How to verify

`jidota start`, close the terminal, open a new one, `jidota status` shows it running; `jidota stop`.

## Acceptance criteria

- [ ] Every command of the table behaves as stated
- [ ] Exit codes follow the table; 0–5 keep the `factory.py` meaning
- [ ] `jidota start` gives the terminal back and the instance survives the terminal on Linux and Windows
- [ ] `jidota clean` never removes a worktree with uncommitted changes
