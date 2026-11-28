# 17 — Generated `--settings` per code repository

**Depends on:** 04, 06
**Reference:** ARCHITECTURE.md §4 (Agents/Settings), §9.1 (Identity: settings, sandbox), §12
(Invariant 13)

## Goal

Write the settings file each agent run of a repository gets with `--settings`: the permissions that
let agents work unattended, and nothing more.

## Job to do

1. Write `<data>/jidota/settings/<host>/<repo>.json` before the first run of a repository, and
   again when its configuration changes.
2. Permissions:
   - **allow**: Read, Grep, Glob; Edit and Write limited to the worktree and the job folder; the
     git commands the agent files use (`git status`, `git diff`, `git log`, `git show`,
     `git branch --show-current`, `git rev-parse`, `git grep`, `git add`, `git commit`,
     `git checkout --`, `git merge`); the build and test commands of the repository;
   - **deny**: `WebFetch`, `WebSearch` (web tools denied by default), `git push`, `git stash`
     (shared by every worktree of a clone, §11).
   Write the rules with the Claude Code permission rule syntax (`Bash(git diff:*)` style).
3. No sandbox: the sandbox is **Not decided** (§9.1). Do not write `sandbox.*` keys.
4. Never `--dangerously-skip-permissions` while runs are not isolated (Invariant 13).

> **Not decided (§9.1):** where the build and test commands of each repository come from — a
> section per repository in `config.json`, a file in the code repository, or the tickets' How to
> check. Recommended: a `repos` section in `config.json`, keyed by `<host>/<repo>`, holding the
> allowed commands (`"dotnet build:*"`, `"dotnet test:*"`). The code repository is untrusted (§3),
> so a file inside it should not grant itself permissions. A repository with no section gets no
> build or test command: its runs fail on the first denial and go to needs-human, which says what
> to add.

## Automated tests

- `Category=Unit`: a repository section with `dotnet build:*` gives `Bash(dotnet build:*)` in allow;
  `WebFetch`, `WebSearch`, `Bash(git push:*)`, `Bash(git stash:*)` are always in deny.
- `Category=Unit`: no `sandbox` key and no bypass mode in any generated file.
- `Category=Unit`: Edit and Write rules name only the worktree and job folder paths.
- `Category=Manual` (excluded from the pipeline): with ticket 02's setup, a generated file makes
  `git push` denied in a real run.

## How to verify

Generate the settings of a test repository and read the JSON; compare with the rules above.

## Acceptance criteria

- [ ] One settings file per repository, under the jidota folder
- [ ] Web tools, `git push` and `git stash` are always denied
- [ ] Writes are allowed only in the worktree and the job folder
- [ ] No sandbox key, no bypass of permissions
- [ ] The source of the build and test commands is the one chosen, recorded in §9.1
