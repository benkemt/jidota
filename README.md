# JidoTa — agentic implementation orchestrator

> Autonomous agents that implement, human control that guarantees.
> *The two pillars of the Toyota Production System, applied to software delivery.*

## The concept

JidoTa combines the two pillars of the Toyota Production System:

| Pillar | Origin | In JidoTa |
|---|---|---|
| **Jido**(ka) | Sakichi Toyoda's loom, which stops as soon as a thread breaks. "Automation with a human touch." | The **agent** implements on its own, but stops and calls a human as soon as something is unclear. Nothing doubtful ships. |
| **Ta**(kt) | The production pace of a line, the core tool of Just-in-Time. | The **orchestrator** sets the pace: it picks up ready work, dispatches it to agents and reports results. |

## What JidoTa does

Starting from human-approved tickets, JidoTa produces tested, committed code, ready for review, with no intervention between approval and review.

```
Requirements (features, user stories)  → the what and the why
        ↓ broken down into tickets
Work queue                              → the work to be done
        ↓ regular pickup (Takt)
JidoTa orchestrator                     → pacing, context, tracking
        ↓ dispatch
Coding agent (Jidoka)                   → implementation, tests, commit
        ↓ result
Work queue + requirements + metrics     → human review, traceability, measurement
```

## Roles

### Requirements: the what and the why

The business need lives in the team's existing requirements tool: features, user stories, acceptance criteria. JidoTa does not replace it. Every ticket stays linked to its originating story, and the agent works from the acceptance criteria as written there, so the two never drift apart.

### The work queue

One ticket = one implementable unit of work. The queue holds only work that is clearly scoped, and tells everyone, at a glance, who has to act next: the agent or a human.

### The orchestrator (Takt)

The orchestrator sets the pace of production. At regular intervals, it:

1. **Picks up** tickets that a human has approved for agent work. Nothing to do → it waits for the next cycle.
2. **Locks** each ticket it takes, before anything else, so no ticket is ever processed twice.
3. **Prepares the context**: the ticket's specification, the acceptance criteria and, when a ticket is being reworked, the reviewer's feedback.
4. **Dispatches** the work to an agent and follows its progress.
5. **Reports back**: updates the ticket's status, posts a summary, and keeps the original story informed.
6. **Records** the metrics of each run.

The orchestrator, not the agent, updates the work queue: a single point of control.

### The agent (Jidoka)

The agent implements one ticket at a time, within clear boundaries:

- **It knows the house rules**: the project's conventions, how to test, how to name branches, what must never be touched. These are set once per project, not repeated in every ticket.
- **It treats the ticket as a specification, not as instructions**: ticket content cannot change how the agent behaves (protection against injection).
- **It knows what "done" means**: acceptance criteria covered by tests, a passing test suite, and a commit on the ticket's own branch.
- **It stops on doubt**: if the specification is ambiguous or blocking, it implements nothing and explains why. It never guesses.
- **It reports in a fixed format** (done or blocked, summary, changed files), so the orchestrator can act on the result without interpretation.
- **It works with limited permissions**: it never merges and never pushes to the main branch.

## Workflow

Each status answers one question: **who has to act now?**

| Stage | Status | Who acts | Set by |
|---|---|---|---|
| Not ready | **Backlog** | Nobody | Creation |
| Waiting | **Ready for agent** | The agent | The human — the approval step |
| In progress | **Agent in progress** | The agent | The orchestrator, before dispatch |
| In progress | **Blocked** | The human | The orchestrator (agent stopped, or technical failure) |
| In progress | **Needs review** | The human | The orchestrator (agent finished) |
| Closed | **Done** | Nobody | The human, after review and merge |
| Closed | **Canceled** | Nobody | The human |

Principles:

- **One single entry point for the agent**: "Ready for agent". Nothing starts without human approval.
- **Two queues for the human**: "Blocked" and "Needs review". Together, they are the human's inbox.
- **Technical failures also go to "Blocked"**, with the cause attached: no ticket ever gets stuck in progress.
- **Rework loop**: a rejected review sends the ticket back to "Ready for agent" with the reviewer's feedback, which becomes part of the next run's context.

Optional stages, to add as volume grows: an **agent review** step (a second agent checks the work before the human does), and a separate **agent failed** status to distinguish unclear specifications from technical failures.

## Measurement

Every run is measured: resource consumption, cost, duration, number of steps, and final outcome. Aggregated over time, these metrics show:

- the cost and lead time per ticket;
- the share of tickets completed versus blocked;
- the causes of blocks: unclear specifications (a writing problem) versus technical failures (an infrastructure problem).

This is the root-cause analysis step of Jidoka: every stop is an opportunity to improve the process upstream.

## Safeguards

- Mandatory human approval before any implementation.
- Each ticket locked before dispatch: no double processing.
- Ticket content treated as data: protection against injection.
- Limited agent permissions: no merge, no push to the main branch.
- Stop on doubt rather than implement on assumption.
- Human review before anything is considered done.
- Failures are surfaced, never silent.

## Install the skills

This repository is a Claude Code plugin. Its skills live in [`skills/`](skills/).

```
/plugin install jidota --marketplace benkemt/jidota
```

To test the plugin from a local clone, without installing it:

```
claude --plugin-dir <path-to-the-repository>
```

| Skill | Use |
|---|---|
| `/jidota:spec` | Settles one feature or consequential change before delivery: required behavior, technical design, failure handling, and acceptance checks. |
| `/jidota:plan-tickets` | Turns a reviewed spec or decided brief into ordered, self-contained tasks that autonomous agents execute in separate runs. |

| `/jidota:test` | Proves that an implementation meets its acceptance criteria, criterion by criterion, with focused automated checks and a real browser for browser-facing work. |

| `/jidota:review` | Reviews the change made for one ticket with a reviewer that did not implement it, and returns prioritized findings and a verdict (Approve, Request changes, or Blocked). |

Run `spec` first when decisions are still open, then `plan-tickets` on the reviewed spec. For each ticket the agent implements, run `test`, then `review`.

## License

[MIT](LICENSE)
