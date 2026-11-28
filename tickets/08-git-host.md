# 08 — Git host: clones, worktrees and the job branch push

**Depends on:** 04, 06, 07
**Reference:** ARCHITECTURE.md §3 (Code repositories), §4 (Hosts/Git, Privilege rules), §5 (Clone,
Worktree), §7.2 (Rollback), §7.4 (Git), §11 (Traps)

## Goal

Every git operation `jidota` makes, in one component, deterministic and with arguments only. It is
the only component that pushes (§4 Privilege rules).

## Job to do

| Operation | Command |
|---|---|
| Clone (first job of a repository; kept) | `git clone <code_repo> <clones>/<host>/<repo>` |
| Update before each job | `git -C <clone> fetch origin` |
| Start branch exists on origin | `git -C <clone> rev-parse --verify --quiet refs/remotes/origin/<start_branch>` |
| Create the worktree (no checkout) | `git -C <clone> worktree add --no-checkout -b factory/<job-id> <data>/jidota/worktrees/<job-id> origin/<start_branch>` |
| Fill the worktree | `git -C <worktree> reset --hard -q` |
| Starting commit of a run | `git -C <worktree> rev-parse HEAD` and `git -C <worktree> status --porcelain` (clean or dirty) |
| Diff and commits of a job | `git -C <worktree> diff origin/<start_branch>...factory/<job-id>` (and `--stat`), `git log --format=%H%x09%s origin/<start_branch>..factory/<job-id>` |
| Push the job branch | `git -C <worktree> push -u origin factory/<job-id>` |
| Remove a worktree | `git -C <clone> worktree remove <worktree>` (never `--force`), then `git worktree prune` |
| Uncommitted changes | `git -C <worktree> status --porcelain --untracked-files=no` |

Rules:

- **Push only `factory/<job-id>`, never with force, never a start branch** (Invariant 2). The push
  method takes a job id, not a branch name, so no other branch can be passed.
- **No checkout under a lock**: create with `--no-checkout`, fill afterwards; on a large repository
  a checkout under the scheduler lock would hold every other decision (trap of §11).
- **A worktree with uncommitted changes is never removed** (Invariant 10): `worktree remove`
  without `--force` refuses; report the reason, keep the worktree.
- Pass branch and URL values after validation (ticket 06), and after `--` where git accepts it.
- Never run a command outside the clones and worktrees of the jidota folder (Invariant 9).

## Automated tests

`Category=Integration`, real `git` on temporary folders: a bare repository as `origin` with a
`main` branch.

- Clone, fetch, worktree from `origin/main`: the worktree is on `factory/<job-id>` at `origin/main`.
- Starting commit: clean after fill; dirty after writing a tracked file.
- Push: the bare repository has `factory/<job-id>`; its `main` is unchanged.
- Remove refuses a worktree with an uncommitted change and keeps it; removes a clean one.
- Fill failure (worktree folder made read-only on Linux) returns the git message.

## How to verify

`dotnet test --filter "Category=Integration&FullyQualifiedName~Git"`.

## Acceptance criteria

- [ ] Each operation of the table runs the exact command shown, with an argument list
- [ ] No method can push a branch other than `factory/<job-id>`; no `--force` anywhere
- [ ] The worktree is created with `--no-checkout` and filled separately
- [ ] A dirty worktree is never removed
- [ ] All tests run in a pipeline with only `git` installed
