# 13 — `jidota init`

**Depends on:** 04, 09, 11, 12
**Reference:** ARCHITECTURE.md §4 (Cli/Init), §5 (Configuration, Schema), §6 (Commands), §11 (To
verify: Status options); features "JidoTa operated from one command", "Ready tickets picked up from
the GitHub Project"

## Goal

Set JidoTa up on a machine in one command: prerequisites, configuration, Status options of the
Project, PostgreSQL container and tables. It runs first, before any spec factory run.

## Job to do

1. **Prerequisites**, each checked and reported as present or missing with how to fix it:
   `claude` signed in, `gh` signed in with the `project` scope (`gh auth refresh -s project`), `az`
   with the `azure-devops` extension, `git`, Docker running.
2. **Ask** which GitHub Project holds the specs and tickets (`owner/number`) and which GitHub
   repository the spec factory creates their issues in (`owner/repo`).
3. **Status field**: the Project's Status has today Todo, Ready, In Progress, Done. Add
   **In Review** and **Needs human** when missing; never remove or rename an option.
4. **Write `config.json`** with the fields of ticket 04 (Project, issues repository, poll interval
   5 min, parallel jobs 3, reviewers security and code, max rework rounds 2, clones folder,
   PostgreSQL connection).
5. **PostgreSQL**: create or reuse the container (ticket 12), store the password (ticket 04), apply
   the migrations (ticket 11).
6. Idempotent: a second `jidota init` keeps the answers as defaults, adds nothing twice, recreates
   nothing.
7. `~/.claude/spec-factory.json` is not read: there is one configuration (features, decisions).

> **To verify (§11):** adding options to a single-select field is a GraphQL mutation
> (`updateProjectV2Field` with the list of options). Check on a test Project that the items already
> at Todo, Ready, In Progress or Done keep their value after the call — if the mutation replaces
> the options with new ids, existing values are lost. Send the existing options with their ids.

## Automated tests

- `Category=Unit`, fakes for every host: missing `gh` scope is reported with the refresh command;
  all present gives an all-green report.
- `Category=Unit`: a Status field with the four options gets exactly two added, the four existing
  sent unchanged with their ids; a field that already has six gets no call.
- `Category=Unit`: second run with an existing `config.json` sends no Status mutation and no
  `docker run`.
- `Category=Integration` (Docker): init with fake `gh`/`claude`/`az` hosts and a test container
  name provisions the container (ticket 12) and creates the tables; the test removes the container.

## How to verify

On a test Project: run `jidota init`, then check the Status options in the GitHub UI and that an
item previously at Ready is still at Ready.

## Acceptance criteria

- [ ] Each prerequisite is reported, with the fix for a missing one
- [ ] In Review and Needs human are added when missing; existing options and item values are kept
- [ ] `config.json` holds every field, with no password
- [ ] The container and tables exist after init; a second init changes nothing
- [ ] `~/.claude/spec-factory.json` is never read
