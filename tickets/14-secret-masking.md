# 14 — Secret masking

**Depends on:** 04, 07
**Reference:** ARCHITECTURE.md §4 (Recording/), §9.3 (Secrets), §12 (Invariants 7, 11); feature
"Code factory runs unattended and records every agent run"

## Goal

A masker that every write to the database and every PR body goes through, so no secret is stored
or published.

## Job to do

1. Build the set of secret values at the start of `serve` and of each run:

   | Source | Rule |
   |---|---|
   | Environment variables | name contains `TOKEN`, `KEY`, `SECRET`, `PASSWORD` or `PAT` (case-insensitive), value at least 8 characters |
   | `gh` token | `gh auth token` |
   | `az` token | the access token of the signed-in account, when signed in |
   | `claude` token | `CLAUDE_CODE_OAUTH_TOKEN` when set; the tokens of `~/.claude/.credentials.json` when the file exists (Linux) |
   | PostgreSQL | the password of `secrets.json` and any connection string holding it |

2. `Mask(string) → string`: replace every occurrence of every secret value with `***`, longest
   value first, before anything is written to `run_lines`, `tool_calls`, a copied job file or a PR
   body (Invariants 7 and 11).
3. The secret set itself is never logged or stored.

> The architecture names "the `gh`, `az` and `claude` tokens" without saying how to obtain them.
> The table above is the recommendation; a source that fails (CLI not signed in, file absent) is
> skipped, never an error.

## Automated tests

- `Category=Unit`: `GITHUB_TOKEN=ghp_abcdefgh123` is masked in a JSON line; `MY_KEY=short` (under
  8 characters) is not; `PATH` is not.
- `Category=Unit`: two secrets where one contains the other are both fully masked.
- `Category=Unit`: a connection string with the password is masked.
- `Category=Unit`: the masker given a fake `gh` that fails still masks the environment values.

## How to verify

`dotnet test --filter FullyQualifiedName~Masking`.

## Acceptance criteria

- [ ] Every source of the table feeds the secret set
- [ ] Values under 8 characters and variables with other names are left alone
- [ ] Masking runs before any database write and any PR body
- [ ] A failing source is skipped without failing the run
- [ ] The secret set never appears in a log
