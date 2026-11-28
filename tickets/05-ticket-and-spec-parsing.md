# 05 — Ticket and spec parsing and validation

**Depends on:** 01
**Reference:** ARCHITECTURE.md §2.2 (YAML), §5 (Ticket, spec; Work item), §9.2 (Input), §11 (Caught
at validation)

## Goal

Turn a GitHub issue body into a typed ticket or spec, or a validation error, before any side
effect. Ticket and spec bodies are untrusted (§9.2).

## Job to do

1. Parse the **first** fenced ```` ```yaml ```` block of the body with YamlDotNet (16.3.0, as in
   `Graph/GraphNet`).
2. A **ticket** has `id`. Fields: `id` (`T<n>`), `key`, `parent_spec` (spec issue URL),
   `depends_on` (list of `T<n>` ids of the same spec, `[]` when none), `code_repo`, `base_commit`,
   `start_branch`, `touches` (a string or a list). Title: the issue title without a `T<n> — `
   prefix (`^T\d+\s*[—–-]\s*`). A ticket whose title contains `[HUMAN]` is a human ticket.
3. A **spec** has `child_specs` and no `id`. Read its `sources` lines: each line marks its role
   ` (scope)` or ` (context)` right after the reference (`^\s*-\s*(.+?)\s*\(scope\)`). An ADO item
   is `ADO #<id>`, a GitHub item is its issue URL; the text after `:` is the title.
4. Validation errors, each with the reason the job will show:

   | Case | Reason |
   |---|---|
   | No yaml block, malformed yaml, or no `id` in a ticket | `invalid ticket yaml` |
   | `depends_on` naming no ticket of the spec | `depends on '<id>', which is no ticket of spec <url>` |
   | A ticket depending on itself | `depends on itself` |
   | Body with neither `id` nor `child_specs` | `neither a ticket nor a spec` |

5. References are compared whole, never by substring: `#33` must never match `#330` (trap of §11).

Constraint: the parser never executes or interprets a value; values reach other modules only as
typed fields.

## Automated tests

- `Category=Unit`, fixtures copied from `Graph/tickets/T1.md`–`T5.md` and the frame of
  `Factory/agents/ticket-writer.md`: each field read; `touches` as string and as list.
- `Category=Unit`: one test per row of the validation table, asserting the reason text.
- `Category=Unit`: a spec with `ADO #1084 (scope)`, `ADO #1086 (scope)` and a `(context)` line
  gives two scope items with their titles; a GitHub issue URL scope item is read as such.
- `Category=Unit`: `depends_on: [T3]` never resolves to `T30`.

## How to verify

`dotnet test --filter FullyQualifiedName~Parsing`.

## Acceptance criteria

- [ ] Every field of a ticket and of a spec is read from the first yaml block only
- [ ] Each validation case gives its exact reason and no partial ticket
- [ ] `[HUMAN]` tickets are flagged from the title
- [ ] Scope work items are read with their tracker, id and title
- [ ] No reference is matched by substring
