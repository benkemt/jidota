# 04 — Configuration, data folder and local secrets

**Depends on:** 01
**Reference:** ARCHITECTURE.md §2.2 (Configuration, Paths, Secret at rest), §5 (Data: Configuration,
Secrets), §8.3 (Limits), §9.1 (Identity), §9.3 (Secrets)

## Goal

Give every command one way to find the `jidota` folder, read `config.json`, and read or write the
local secrets, on Windows and Linux.

## Job to do

1. `<data>` = `Environment.SpecialFolder.LocalApplicationData`: `%LOCALAPPDATA%` on Windows,
   `$XDG_DATA_HOME` or `~/.local/share` on Linux. The jidota folder is `<data>/jidota/`. Build
   every path with `Path.Combine`, never a hard-coded separator.
2. `config.json`, read with `System.Text.Json` into typed options. Fields and defaults:

   | Field | Default |
   |---|---|
   | GitHub Project (`owner/number`) | asked by `jidota init` |
   | Issues repository (`owner/repo`) | asked by `jidota init` |
   | Poll interval | 5 min |
   | Parallel jobs | 3 |
   | Reviewers | `security`, `code` |
   | Max rework rounds | 2 |
   | Run duration | 60 min |
   | Run budget | 10 USD |
   | Clones folder | `<data>/jidota/clones` |
   | PostgreSQL connection (host, port, database, user; no password) | set by `jidota init` |
   | API and dashboard port | **Not decided** (§8.3): keep it a field; pick a default and record it in a comment |
   | Quota warning threshold (`utilization`) | **Not decided** (§8.3): field with no default; no threshold when absent |

3. `secrets.json` holds the PostgreSQL password. Windows: encrypted with DPAPI for the current
   user (`System.Security.Cryptography.ProtectedData`). Linux: file mode 0600
   (`File.SetUnixFileMode`). The OS check `OperatingSystem.IsWindows()` lives here, in one place.
4. `api.token`: random token file, written owner-only like `secrets.json` (used by ticket 31).
5. A missing `config.json` is an error that says to run `jidota init` (the spec factory relies on
   it, ticket 38).

Constraint: no secret ever goes into `config.json`, a log line or an error message (Invariant 11).

## Automated tests

- `Category=Unit`: round trip of `config.json` with every field; defaults applied when absent.
- `Category=Unit`: path resolution uses `LocalApplicationData` (inject the base folder).
- `Category=Unit` (Windows only, `SkippableFact`): a password written to `secrets.json` is not in
  clear text in the file and reads back.
- `Category=Unit` (Linux only): `secrets.json` and `api.token` have mode 0600 after writing.
- `Category=Unit`: a missing `config.json` gives the error naming `jidota init`.

## How to verify

Write a config and a secret through a small test harness, then inspect the files: no password in
`config.json`; `ls -l` on Linux shows `-rw-------`.

## Acceptance criteria

- [ ] The same code finds `<data>/jidota/` on Windows and Linux
- [ ] Every field of the table is read, with its default
- [ ] The password is never written to `config.json`
- [ ] On Linux, `secrets.json` and `api.token` are 0600; on Windows the password is DPAPI-protected
- [ ] A missing configuration fails with a message naming `jidota init`
