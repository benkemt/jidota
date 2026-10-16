---
name: plan-tickets
description: "Turns a reviewed spec or decided brief into ordered, self-contained tasks that autonomous agents execute in separate runs with minimal exploration and trial and error. Use for implementation tasks, tracker tickets, or milestones meant for agent execution. Do not use for a single coding task or its short execution outline."
user-invocable: true
argument-hint: "<spec, brief, issue, or request>"
disable-model-invocation: true
---

# Plan agent tasks

Create tasks that a fresh agent can finish in one run without making product or technical decisions, without asking questions, and with as little searching and retrying as possible.

The planner has already read the source and the code. Most of an agent's time goes into reading them again and guessing how to verify its work. Each task must hand over what the planner learned: where to start, which pattern to follow, how to check quickly, and when to stop.

Every task and milestone is a vertical slice: a usable outcome that runs through the required layers and has acceptance checks. Split by working result, not by file, layer, or team boundary.

## Process

1. Read the source, the repository instructions (`CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, or equivalents), and the relevant code. Record the base commit with `git rev-parse --short HEAD`. When the source is a spec written with the `spec` skill:
   - stop and say so if it has a blocking open decision;
   - start from its Codebase pointers and verify them at the current commit instead of searching again; if `base_commit` differs from `HEAD`, check only the cited files with `git diff --stat <base_commit> HEAD -- <paths>`;
   - take its contracts, examples, and `assumed` defaults as decided.
2. While reading, note for each future task:
   - the entry points: files, symbols, and the test file to extend;
   - an existing example in the repository that the agent should imitate;
   - the narrowest test command that covers the change;
   - prerequisites: tools, services, credentials, permissions, and test data;
   - pitfalls: generated files, flaky tests, encoding, path or platform quirks.
3. Stop and send the source back to the `spec` skill (`/jidota:spec`) if an unresolved choice would change behavior, interfaces, data, security, scale, performance, compatibility, operations, cost, or proof. If only an experiment can answer a technical unknown, create a spike task. It asks one precise question, sets a time limit, and says what form the answer takes.
4. Split the work into tasks. Each one delivers working behavior, fits one agent run (see Sizing), and produces one focused pull request.
5. Keep each shared contract in one task. That task fixes the exact signatures, schemas, file formats, and error messages. Later tasks depend on it and refer to it. Two tasks must never answer the same question independently.
6. Put refactoring in its own task when it would hide a behavior change.
7. Order tasks by dependency. Put tasks in the same parallel group when neither depends on the other and their `touches` lists do not overlap.
8. Group tasks into milestones when useful. Each milestone delivers a usable end-to-end result with acceptance checks and dependencies. Do not use milestones such as "database", "backend", or "frontend".
9. Before returning, check that every path, symbol, and command you cite exists at the base commit, then run each task's `check_fast` and `check_full` there. Each one must succeed before any change; a test filter that matches no test yet is fine when all its tests are new. When a command already fails, replace it with one that succeeds, such as the per-project commands the CI runs. If none exists, write the expected failure into the task and say so in the plan, because an agent cannot tell an existing failure from one it caused.
10. Return the plan in chat. Create tracker tickets only when the user asks. Never write a plan document.
11. Stop after planning. Do not implement.

For example, "add a task and see it after a restart" includes CLI input, validation, storage, output, and tests in one task. A later milestone could deliver "manage unfinished tasks" through add, list, and complete slices. Name the milestone's observable result and how to prove the whole result works.

## Sizing

A task fits one agent run when, as a rough guide:

- it changes eight files or fewer, with a diff of about 400 lines or less;
- it introduces at most one new contract (interface, schema, endpoint, or file format);
- every item in Done when can be proven with one fast check command plus the full check.

Split the task if it needs a second new fixture, a second entry point, or a second unrelated test area. Merge two tasks if neither one delivers a checked outcome on its own.

## Write for two readers

A human reads each task and an agent executes it.

A human must understand the title, What are we building?, and Why? in under a minute. State the concrete problem, the result, and why it matters in everyday words. Do not put requirement IDs, implementation details, undefined project terms, or unfamiliar acronyms there.

Agent notes hold what the agent needs to start quickly and finish safely. Write them as short bullets, not prose. Link the spec or decided source for shared architecture and full requirement definitions. Use a repository path or URL that will resolve from the published ticket, and pin the version when later edits could change the contract. If there is no durable source, put the required shared decisions in Agent notes. Never copy the whole source into a ticket.

Facts that apply to the whole repository, such as build commands, conventions, and global pitfalls, belong in the repository instructions, not in each ticket. If they are missing, list them in the plan under "Repository instructions to add".

## Task shape

Use this shape. Omit optional fields and sections that add no information.

````markdown
## <Plain action and result>

```yaml
id: T3
depends_on: [T1]
parallel_group: B
base_commit: <short sha>
start_branch: <branch the work starts from and the pull request targets, when it is not the remote default branch>
touches: [<paths or globs this task changes>]
check_fast: <narrowest command, run often>
check_full: <full command, run once before the pull request>
```

### What are we building?
In one to three short sentences, say what is wrong or missing and what will work after this task.

### Why?
In one or two short sentences, explain the practical value to a user, operator, or developer.

### Done when
- Three to seven observable results. Each one is proven by an item in How to check. Mark each one `[new]` when the behavior does not exist yet, or `[kept]` when the change must not break it.

### How to check
- Fast: `<check_fast>`, which runs only this task's tests. Before the change: each `[new]` test fails on its assertion, with the reason (for example `header X-Content-Type-Options missing`), and each `[kept]` test passes. After the change: all pass.
- Full: `<check_full>`, with the expected result.
- Manual: exact steps and the expected observation, only when automation cannot cover the behavior.

### Agent notes
- Source: <durable spec, brief, issue, or request, pinned when needed>
- Start here: <files, symbols, test file to extend>
- Follow: <existing example to imitate, as path:line>
- Do not modify: <generated files, contracts owned by another task>
- Prerequisites: <tools, services, credentials, data; mark [HUMAN] for steps an agent cannot do>
- Decisions: <only the decisions, definitions, and failure rules specific to this task>
- Examples: <input → expected output, including error cases, as a small table when there are several>
- Pitfalls: <traps found while planning>
- Stop if: <assumption that could be false> → stop and report what you found. Do not work around it.
- Allowed defaults: <minor choices the agent may make alone; list each one in the pull request description>

### Out of scope
- Related work this task is likely to absorb by mistake.
````

## Writing rules

- Use a short title that names an action and a result.
- Use familiar words and specific verbs.
- Define a necessary technical term where it first appears. Otherwise replace it with observable behavior.
- Say `sending the same event twice creates one reply`, not `prove idempotency`.
- Say `the answer is supported by the cited document`, not `prove grounding`.
- Prefer concrete examples with real values over descriptions of rules.
- Point to existing code. Do not write the implementation or step-by-step coding instructions into the ticket, because they break as soon as the code moves.
- When the repository already settles a local mechanic (naming, error handling, test layout), point to it. Otherwise leave interchangeable mechanics to the agent.
- Do not add user stories by default. Add one only when it clarifies product behavior that the first two sections do not.
- Preserve applicable `AC-n`, `REQ-n`, and `INV-n` references in Done when or Agent notes. Keep each ID attached to the same rule. Never renumber or reuse one.
- Keep the human sections under about 120 words. Aim for 300 to 600 words per ticket in total. Exceed 800 only when the extra text prevents an unsafe or incompatible implementation. Otherwise split the task or link the shared source.
- Do not repeat a fact in several sections.
- Do not use slogans, metaphors, filler, or vague claims such as `robust`, `seamless`, `comprehensive`, and `future-proof`.

## Boundaries

- Do not split one working behavior into separate file or technical-layer tasks.
- Do not create scaffolding or cleanup tasks without a checked outcome.
- Do not hide unresolved decisions inside implementation tickets.
- Do not let two tasks in the same parallel group touch the same files.
- Do not give an agent a task that needs a [HUMAN] prerequisite before that prerequisite is done. Say so in the plan.
- Every Done when item has a proof in How to check, and every check states its expected result.
- When the source is a spec, every one of its `AC-n` appears in the Done when of at least one task, agent or `[HUMAN]`. Say in the plan which task covers which `AC-n`.

## Review passes

Read each task four times before returning the plan:

1. Human pass: can someone explain what will change and why after reading only the title and the first two sections?
2. Agent pass: can a fresh agent find the source, the dependencies, and the fixed decisions, implement the task, and prove it without asking a product or architecture question?
3. Cost pass: can a fresh agent start editing within a few minutes, without open-ended searching? If not, add the missing pointer, example, or command.
4. Readiness pass: answer each question below with evidence from the code or a command, and fix the task until every answer is yes.
   - **Proof.** Can an agent prove every Done when item with a command, or with a test whose location is given and that fails if the behavior breaks? A criterion only a human can prove (a security scan, production access, a manual start, a visual judgment, a sign-off) goes into a separate `[HUMAN]` task that depends on this one, never into an agent task's Done when. When the spec's proof of an `AC-n` has a part this task does not run, say where that part is covered.
   - **Touches.** Walk through the change up to the first edit, for each Done when item. Is every file it needs in `touches`: types the tests must see, registrations, project files, migrations, fixtures, shared test setup? When the task must not change a shared file, say how to work without it, for example by configuring the test host instead of editing the shared fixture.
   - **Allowed defaults.** Does every choice an Allowed default leaves open stay inside `touches`? When a default lets the agent pick a name or a folder, `touches` uses a glob that covers every allowed choice.
   - **Red first.** Is every Done when item marked `[new]` or `[kept]`? Does `check_fast` select only this task's tests, and does How to check say why each `[new]` test fails before the change?
   - **Commands.** Did `check_fast` and `check_full` succeed at the base commit (step 9)?
   - **Branch.** When the work does not start from the remote default branch, or the repository instructions do not say where pull requests go, does `start_branch` say it?
   - **Source.** Does the pin name the version you read? When the tracker only serves the current version, pin its last update time at planning.

   When an answer needs a choice you cannot make alone, such as moving a criterion to a `[HUMAN]` task or building a test an agent can run for it, ask the user before creating the tickets. An answer that stays no is a blocking decision in the plan.

After all four passes succeed, delete repeated background. `/jidota:check` asks the readiness questions again, with a fresh agent, when the tickets reach Review: a task that passes the readiness pass leaves it nothing to find.

## Return

Return, in this order:

1. The base commit and any check that already fails before any change.
2. The ordered tasks, with dependencies and parallel groups.
3. Useful milestones with their acceptance checks.
4. [HUMAN] prerequisites to complete before the runs start.
5. Decisions that still block implementation.
6. Repository instructions to add, if any.

Do not add a separate summary that repeats the tasks.
