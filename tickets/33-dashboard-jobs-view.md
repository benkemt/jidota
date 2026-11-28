# 33 — Dashboard: Jobs view and human actions

**Depends on:** 25, 31
**Reference:** ARCHITECTURE.md §2.2 (Local API, dashboard), §6 (Local API: the dashboard calls the
same routes), §9.2 (HTML in the dashboard), §10 (Dashboard); features "Cost and time visible per
work item" (Jobs view), "Jobs started and released from the dashboard"

## Goal

The first page of the dashboard: what runs now, what waits for a human, what each job cost so far,
and the buttons that act on jobs.

## Job to do

1. Blazor Server page in `Web/`, live over SignalR, served by the running instance on
   `127.0.0.1`; access through the token cookie (ticket 31).
2. Content:
   - every job as a card at its stage: build, review, approve, PR, done;
   - jobs that wait for a human (needs-human, blocked) stand out with their reason;
   - running jobs against the parallel-jobs limit (`running 2 / 3`);
   - the pause state (`paused: quota` until a time, `paused: auth`) and the last quota warning;
   - each card: ticket, spec, repository, round and reviewer verdicts, PR link, cost so far
     (labelled as an estimate);
   - the card opens the job: its files (`spec.md`, `build.md`, reviews, `decision.md`), its runs.
3. Actions, through the same routes as the CLI (ticket 31): start a ticket or a spec (refusal
   reason shown, e.g. a dependency not Done), approve, rework with a note, cancel (with a
   confirmation).
4. Text from tickets, files and runs is rendered as text, never as HTML (Blazor encoding; markdown
   shown as text — §9.2).
5. Single user; no sharing (feature non-goal).

Keep the logic in a data service and an API client the components receive by injection, so
components can be tested with bUnit (§2.2) against fakes.

## Automated tests

- `Category=Integration` (Testcontainers): the jobs query returns cards grouped by stage, with
  reason, round verdicts and cost so far for a seeded database.
- `Category=Unit` (bUnit, fake API client and data service):
  - clicking Cancel shows a confirmation; confirming calls `POST /api/jobs/{id}/cancel`; dismissing
    calls nothing;
  - Rework sends the typed note verbatim to `POST /api/jobs/{id}/rework`; an empty note sends
    nothing;
  - Approve is shown only on a needs-human card and calls the approve route;
  - starting a ticket that the API refuses with 422 shows the refusal and the dependencies not Done;
  - a job update pushed by the data service moves the card from build to review without a reload;
  - `running 2 / 3` and `paused: quota until <time>` are rendered from the status.
- `Category=Integration` (`WebApplicationFactory`): the page without the cookie → 401; with it,
  200.
- `Category=Integration`: a ticket title `<script>alert(1)</script>` appears encoded in the HTML.

## How to verify

`jidota status`, open the dashboard URL, start a test ticket, watch its card move from build to PR.

## Acceptance criteria

- [ ] Cards show every job at its stage, live
- [ ] Jobs that wait for a human show their reason
- [ ] Running jobs are shown against the limit, and the pause state is visible
- [ ] Start, approve, rework and cancel use the same routes as the CLI
- [ ] Cancel asks for a confirmation before calling the API
- [ ] No ticket or run text is rendered as HTML
