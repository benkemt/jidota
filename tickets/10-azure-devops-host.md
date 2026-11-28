# 10 — Azure DevOps host: draft PRs and work item links

**Depends on:** 06, 07
**Reference:** ARCHITECTURE.md §3 (PRs on Azure DevOps), §4 (Hosts/AzureDevOps), §8.3 (ADO PR
description), §9.2 (Text sent to az)

## Goal

Every `az` call for PRs on Azure DevOps Repos behind one interface, with the same operations as the
GitHub host, plus the link to the `(scope)` work items.

## Job to do

All commands end with `--organization https://dev.azure.com/<org> -o json`; `<org>`, `<project>`,
`<repo>` come from the remote patterns of ticket 06 (URL-decoded).

| Operation | Command |
|---|---|
| Find the open PR of a branch | `az repos pr list --project <project> --repository <repo> --source-branch <branch> --status active` |
| Create a draft PR | `az repos pr create --draft true --project <project> --repository <repo> --source-branch <branch> --target-branch <start_branch> --title <subject> --description @<file>` (`pullRequestId` in the output) |
| Update a PR | `az repos pr update --id <n> --title <subject> --description @<file>` |
| PR state | `az repos pr show --id <n>`: `status` `active` → OPEN, `completed` → MERGED, other → CLOSED; merge commit `lastMergeCommit.commitId` |
| Close a PR (cancel) | `az repos pr update --id <n> --status abandoned` |
| Link work items | `az repos pr work-item add --id <n> --work-items <id> <id> …` |

PR URL: `https://dev.azure.com/<org>/<project>/_git/<repo>/pullrequest/<n>`, each part URL-encoded.

Rules and traps:

- **The ADO description is limited to 4000 characters** (`ADO_DESCRIPTION_MAX` in `factory.py`):
  cut the body at 3920 characters and append `… truncated: see <job folder>`.
- **Text goes through a file** (`--description @<file>`), never as an argument (§9.2).
- Nothing is read from or written to the work item itself; only the PR link is added (§1 non-goal).
- Network calls use the retry of ticket 07.

## Automated tests

- `Category=Unit`, fake `IProcessRunner`: each operation sends the exact argv of the table.
- `Category=Unit`: parsing of recorded `az` outputs (`Fixtures/az/`): create, list, show for each
  status.
- `Category=Unit`: a 4500-character body becomes 4000 characters at most, ending with the pointer.
- `Category=Unit`: an organization or project with a space gives a correctly encoded URL.

## How to verify

`dotnet test --filter FullyQualifiedName~AzureDevOpsHost`.

## Acceptance criteria

- [ ] Every operation of the table builds the exact argv shown
- [ ] `active`, `completed` and other statuses map to OPEN, MERGED, CLOSED
- [ ] A description never exceeds 4000 characters
- [ ] No call writes to a work item other than the PR link
- [ ] All tests run without `az` installed
