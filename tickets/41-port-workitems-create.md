# 41 — Port `workitems.py create` to `jidota workitems create`

**Depends on:** 40
**Reference:** ARCHITECTURE.md §4 (WorkItems/), §6 (Commands, Compatibility), §9.2 (Text sent to
az), §12 (Invariant 12)

## Goal

The write half of the workitems skill through `jidota`: create exactly the plan that was checked,
resumable after an error.

## Job to do

```
jidota workitems create <document> [--batch <n>] [--dry-run]
```

1. **Refuse a plan changed since its last clean `check`** (fingerprint of ticket 40) → exit 3.
2. Create the items **top-down**, each with its parent link, then add the Predecessor / Successor
   links, always on a new item; at most `--batch` new items per call (default 10).
3. Record each created id in `created.json` and each link in `links.json` as it goes; **stop at the
   first error and resume where it stopped** on the next call.
4. **Every value goes to `az` through a file (`@file`)**, so no HTML is parsed by a shell (§9.2).
5. No tags are ever set.
6. `--dry-run` prints the `az` commands and creates nothing.
7. Exit codes: 0 ok, 1 error, 3 the plan breaks a rule. JSON on stdout.

## Automated tests

- `Category=Unit`, fake `az`: a 1 Epic / 2 Features / 3 Stories plan is created parents first; the
  calls equal the golden sequence recorded from `workitems.py`.
- `Category=Unit`: a fake `az` failing at the 4th item stops there; the next call creates from the
  4th, with no duplicate.
- `Category=Unit`: `plan.json` edited after `check` → exit 3, no `az` call.
- `Category=Unit`: no `az` argument holds description HTML (it is always `@<file>`); no tag argument.
- `Category=Unit`: `--batch 2` creates two items per call.

## How to verify

`jidota workitems create <doc> --dry-run` on a checked test plan prints the same `az` commands as
the Python script.

## Acceptance criteria

- [ ] A plan changed since its last clean check is refused
- [ ] Items are created top-down with their parent, links added after
- [ ] A failure stops the run and the next call resumes without duplicates
- [ ] Values only reach `az` through files; no tags
