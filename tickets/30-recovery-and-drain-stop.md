# 30 — Startup recovery, drain stop and single instance

**Depends on:** 11, 21, 23, 28
**Reference:** ARCHITECTURE.md §1 (guarantee: a job survives a stop, a crash or a reboot), §7.3
(Recovery), §7.4 (One instance per machine), §11 (Runtime: `jidota` crashes during a run, `jidota
stop` during runs); feature "JidoTa operated from one command"

## Goal

Make `serve` safe to stop, kill or reboot: a drain stop never interrupts a run, and every start
picks each job up where it stopped.

## Job to do

1. **Single instance**: at start, take the advisory lock (ticket 11) and refuse to run without it,
   and refuse a database behind its migrations.
2. **Recovery**, on every start:
   1. runs still `running` in the database have no process: they end `crashed`;
   2. each job not in done, cancelled, needs-human or blocked resumes at its stage: a crashed run is
      started again once (second failure → needs-human); a job between two runs starts its next run;
   3. the Status of every ticket with an open job is written again from its job (ticket 21).
3. **Drain stop** (`jidota stop`): no new job and no new run starts; each running run finishes; then
   the process exits. A job between two runs carries on at its next step on the next start.
4. The operator only runs `jidota start`; a job left in needs-human by the recovery is released with
   `approve` or `rework` (ticket 29).

## Automated tests

`Category=Integration`, FakeClaude + Testcontainers:

- Kill `serve` (in-process host stopped abruptly) during a `hang` run; start again: the run is
  `crashed`, a new attempt starts; a second crash → needs-human.
- A job committed at `review` with no run: on start, its reviewers start.
- Drain stop during a run: the run reaches `finished`, no next run starts, the host exits; on the
  next start the job continues at its next stage.
- A second `serve` against the same database refuses to start.
- On start, a ticket whose Status differs from its job is written again.

## How to verify

Start `serve` with a job running, `jidota stop`, check the run finished; start again, check the
job goes on.

## Acceptance criteria

- [ ] `jidota stop` never interrupts a running agent run (feature success criterion)
- [ ] After a crash, every unfinished job resumes at its stage, crashed runs started again once
- [ ] Two instances never run against one database
- [ ] Ticket Statuses are rewritten from their jobs at start
