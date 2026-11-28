# 09 — GitHub host: Project items, Status, issues and draft PRs

**Depends on:** 07
**Reference:** ARCHITECTURE.md §3 (GitHub Project + issues, PRs on GitHub), §4 (Hosts/GitHub), §9.2
(Text sent to gh), §11 (Traps)

## Goal

Every `gh` call of `jidota` behind one interface: read the Project and its tickets, write a Status,
and open, update, read and close draft PRs on GitHub.

## Job to do

| Operation | Command (all with `--format json` / `--json` where the command has it) |
|---|---|
| Project fields (Status field id and option ids) | `gh project field-list <number> --owner <owner>` |
| Project items with their Status | `gh project item-list <number> --owner <owner> --limit <n>` |
| Write a Status | `gh project item-edit --id <item-id> --project-id <project-id> --field-id <field-id> --single-select-option-id <option-id>` |
| Read an issue | `gh issue view <n> -R <repo> --json number,title,body,state,url` |
| Sub-issues of a spec | `gh api repos/<repo>/issues/<n>/sub_issues?per_page=100` |
| Find the open PR of a branch | `gh pr list -R <repo> --head <branch> --state open --json number,url` |
| Create a draft PR | `gh pr create -R <repo> --draft --base <start_branch> --head <branch> --title <subject> --body-file <file>` (the URL is the last stdout line) |
| Update a PR | `gh pr edit <n> -R <repo> --title <subject> --body-file <file>` |
| PR state | `gh pr view <n> -R <repo> --json state,mergeCommit` → `OPEN`, `MERGED`, `CLOSED` |
| Close a PR (cancel) | `gh pr close <n> -R <repo>` |

Rules and traps:

- **Text goes through a file**: PR bodies always via `--body-file` (§9.2), never as an argument.
- **`gh project` needs the `project` scope** (`gh auth refresh -s project`); an error mentioning
  the scope is reported with that command as the hint.
- **Pass `--limit`** large enough for the whole Project: `gh` pages project items with a default
  limit. Check `gh project item-list --help` for the current default.
- A PR is always a draft; no method marks a PR ready, approves or merges it (Invariant 2).
- Network calls use the retry of ticket 07.

## Automated tests

- `Category=Unit`, fake `IProcessRunner`: each operation sends exactly the argv of the table.
- `Category=Unit`: parsing of recorded `gh` JSON outputs (`Fixtures/gh/`): field list, item list
  with Status values, sub-issues, PR list, PR view for each state.
- `Category=Unit`: `gh pr create` stdout with a warning line before the URL gives the URL and the
  number.
- `Category=Unit`: a scope error gives the `gh auth refresh -s project` hint.

## How to verify

`dotnet test --filter FullyQualifiedName~GitHubHost`. Manually, once: list the items of a test
Project with the host and compare with the GitHub UI.

## Acceptance criteria

- [ ] Every operation of the table builds the exact argv shown
- [ ] PR bodies are only passed through a file
- [ ] No method can mark a PR ready, approve or merge
- [ ] The three PR states and the merge commit are read from `gh pr view`
- [ ] All tests run without `gh` installed
