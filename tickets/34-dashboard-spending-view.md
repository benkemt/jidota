# 34 — Dashboard: Spending view

**Depends on:** 25, 33
**Reference:** ARCHITECTURE.md §5 (Agent run, Work item), §10 (Dashboard: what a work item cost);
feature "Cost and time visible per work item"

## Goal

Show what each work item cost to implement: cost, tokens and time per ADO work item, per ticket, per
job and per agent, and their trend over time.

## Job to do

1. Totals of cost (`total_cost_usd`), tokens (input, output, cache-creation, cache-read) and time
   (wall-clock and API) at four levels: work item → its tickets → their jobs → each agent.
2. **Shared costs**: a job linked to several `(scope)` work items counts in full for each of them.
   Mark those costs as shared, since their sum is more than the real total.
3. **Estimate**: cost is the `total_cost_usd` reported by `claude -p`; on a subscription token it is
   an estimate, not a bill. Label it as such on the page.
4. **Unfinished runs** have no cost: count their tokens and time, and show them as runs with no
   cost.
5. **Trend over time**: the same totals per day or week.
6. A work item is shown with its tracker, id and title only (nothing is read from ADO; no story
   points comparison — feature non-goal).

> Whether a `--resume` run's `total_cost_usd` counts from that run or from the start of the session
> is answered in ticket 02's fixture README. When it counts from the start, subtract the previous
> run of the session before summing.

## Automated tests

`Category=Integration` (Testcontainers), seeded runs:

- One work item, two tickets, three jobs, four agents: each level's totals equal the sum of its
  runs.
- A job linked to two work items: its cost is in both, both marked shared; the grand total counts
  it once.
- A crashed run adds tokens and time but no cost, and is listed as no-cost.
- A resumed session: the job total follows the rule of ticket 02's answer.

`Category=Unit` (bUnit, fake spending service):

- the estimate label is rendered next to every cost;
- a shared cost is rendered with its shared marker; a run with no cost shows "no cost", not `$0.00`;
- expanding a work item shows its tickets, then a ticket its jobs, then a job its agents;
- switching the trend from day to week asks the service for the weekly totals.

## How to verify

Seed or run two jobs, open Spending, and compare a work item's total with the sum of its runs in
SQL.

## Acceptance criteria

- [ ] Totals at work item, ticket, job and agent level match the stored runs
- [ ] Shared costs are marked and not double-counted in a grand total
- [ ] Cost is labelled as an estimate
- [ ] Runs without cost are shown as such
- [ ] A trend over time is shown
