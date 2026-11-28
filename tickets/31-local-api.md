# 31 — Local API and its token

**Depends on:** 04, 28, 29, 30
**Reference:** ARCHITECTURE.md §6 (Local API, Errors, Compatibility), §9.1 (callers), §9.2
(Cross-site calls), §9.3 (API token)

## Goal

The HTTP API of the running instance that the CLI and the dashboard both call, listening on
`127.0.0.1` only, with a token on every route.

## Job to do

1. Minimal API in `Web/`, bound to `127.0.0.1` on the port of `config.json`.
2. `jidota start` writes a new random token to `<data>/jidota/api.token` (owner-only, ticket 04) at
   each start. Every route requires it: the CLI sends it as a header; the dashboard URL given by
   `jidota status` carries it once and sets a cookie.
3. Routes:

   | Route | Effect |
   |---|---|
   | `GET /api/status` | instance state (running, paused with reason and resume time), jobs, slots, last poll |
   | `POST /api/jobs` `{ "target": "<ticket or spec issue URL>" }` | run (ticket 29) |
   | `POST /api/jobs/{id}/approve` | approve |
   | `POST /api/jobs/{id}/rework` `{ "note": "…" }` | rework |
   | `POST /api/jobs/{id}/cancel` | cancel |
   | `POST /api/stop`, `POST /api/resume` | drain stop (ticket 30), resume (ticket 28) |

4. Errors:

   | HTTP | Meaning |
   |---|---|
   | 200 / 202 | done / accepted |
   | 422 | `[HUMAN]` ticket; not eligible (Status not Ready, or a dependency not Done, with the list) |
   | 409 | open job, wrong stage, run active; busy (touches or slots) |
   | 401 | missing or wrong token |
   | 404 | unknown job or issue |

   The body says which case it is, so the CLI maps it to its exit code (ticket 32).
5. Not versioned: the only client is the one installed with it.

## Automated tests

`Category=Integration`, `WebApplicationFactory` with fake `Jobs/`:

- Every route without the token → 401; with a wrong token → 401.
- Each error case of the table → its status and body.
- The server binds to `127.0.0.1` and not to `0.0.0.0` (inspect the configured URLs).
- `GET /api/status` during a quota pause shows `paused: quota` and the resume time.

## How to verify

`curl -H "<token header>: <token>" http://127.0.0.1:<port>/api/status` returns the status; without
the header, 401.

## Acceptance criteria

- [ ] Listens on `127.0.0.1` only
- [ ] Every route requires the token, regenerated at each start
- [ ] Each route calls the same code as the CLI action
- [ ] Each error maps to the status of the table
