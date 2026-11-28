# 06 — Job naming, touches overlap and remote patterns

**Depends on:** 05
**Reference:** ARCHITECTURE.md §5 (job id), §7.4 (Touches), §9.2 (Validation, Path traversal,
Option injection)

## Goal

Port the pure functions of `factory.py` that name jobs, compares `touches` and recognises a code
repository host, so the scheduler and the PR stage share one tested implementation.

## Job to do

1. **Commit subject** (also the PR title): `T<n> - <ticket title> (<key>)`.
2. **Slug**: words `[a-z0-9]+` of the lower-cased title, stop words removed
   (`a an the and or of on in to for from with by at is`), first 4 words joined by `-`, at most
   40 characters, `ticket` when empty.
3. **Job id**: `<seq>-<ticket id lower-cased>-<slug>`, `seq` three digits, one sequence across all
   repositories (ticket 11 stores it). Branch: `factory/<job-id>`. The job id only holds
   `[a-z0-9-]`, so it is safe as a folder name (§9.2).
4. **Touches overlap** (`overlap()` of `factory.py`): paths normalised (`\` → `/`, leading `./`
   removed, lower-cased); two paths overlap when equal, or when one ends with `/` and the other
   starts with it; an empty or missing `touches` overlaps everything. Overlap is computed only
   between tickets of the **same** code repository.
5. **Remote patterns**, from `factory.py`:

   ```
   ORIGIN_GH      github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$
   ORIGIN_ADO     dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/]+?)/?$
   ORIGIN_ADO_SSH ssh\.dev\.azure\.com:v3/([^/]+)/([^/]+)/([^/]+?)/?$
   ORIGIN_VS      ([^/.@]+)\.visualstudio\.com/(?:DefaultCollection/)?([^/]+)/_git/([^/]+?)/?$
   ```

   A `code_repo` matching none is `unknown host`. The repository key (`<host>/<repo>`) names the
   clone folder.
6. **Option injection**: a `start_branch` or a branch value starting with `-`, or holding a
   character git refuses in a ref name, is rejected before use.

## Automated tests

- `Category=Unit`: subject and job id for `T4` "Fallback warning on Windows Server 2016" with key
  `#36` and seq 3: `003-t4-fallback-warning-windows-server`.
- `Category=Unit`: overlap table — equal paths, folder prefix `installer/`, different case and
  `\`, empty touches, same path in two repositories (no overlap).
- `Category=Unit`: each remote pattern with an HTTPS and an SSH sample; `https://gitlab.com/x/y`
  is `unknown host`.
- `Category=Unit`: `start_branch: --upload-pack=x` is rejected.

## How to verify

`dotnet test --filter FullyQualifiedName~Naming`.

## Acceptance criteria

- [ ] Subject, slug and job id match the `factory.py` rules on the samples above
- [ ] Overlap never compares tickets of two repositories
- [ ] A ticket with no `touches` overlaps every ticket of its repository
- [ ] Every Azure DevOps and GitHub remote form above is recognised; others are `unknown host`
- [ ] Branch values starting with `-` are rejected
