# 38 — Port `publish_github.py` to `jidota spec publish`, destination from the configuration

**Depends on:** 04, 05, 09
**Reference:** ARCHITECTURE.md §4 (Spec/), §5 (Configuration), §6 (Commands, Compatibility), §12
(Invariant 12); features (decisions: one configuration; "JidoTa operated from one command")

## Goal

Publish a spec and its tickets as GitHub issues through `jidota`, always to the Project and issues
repository of the jidota configuration, and refuse to run before `jidota init`.

## Job to do

Port `Factory/skills/spec-factory/scripts/publish_github.py`:

```
jidota spec publish --target [specs/<slug>]     # print the destination, change nothing
jidota spec publish specs/<slug> --dry-run      # show what would be created
jidota spec publish specs/<slug>
```

1. **Destination**: the Project and the issues repository of `config.json` only. No
   `config.json` → error that says to run `jidota init`, before anything is read (feature success
   criterion). `~/.claude/spec-factory.json` is not read.
2. Behaviour kept from the script:
   - the spec becomes one issue titled `Spec <refs> — <title>`, refs grouped by tracker from the
     `(scope)` sources (`Spec ADO #1084, #1086 — …`); no scope item → exit 2;
   - each ticket becomes an issue (title without `T<n> — `), attached as a sub-issue
     (`POST repos/<repo>/issues/<spec>/sub_issues` with the issue id), and added to the Project;
     `Content already exists in this project` is not an error (a Project workflow may have added it);
   - local files updated as it goes: `parent_spec` and `key` (`"#<n>"`) in each ticket,
     `child_specs` in the spec, and the spec issue body edited at the end;
   - every created issue recorded in `published.json` right away, so a second run after a partial
     failure creates only what is missing;
   - bodies always through `--body-file`.
3. Exit codes: 0 published, 1 GitHub or CLI error, 2 invalid spec folder.

> **Contradiction to settle**: Invariant 12 says the ported subcommands keep the inputs of their
> script, but the features say the destination comes from the jidota configuration, "not from
> `--repo` / `--project`, `published.json` or `~/.claude/spec-factory.json`". Follow the features:
> drop `--repo` / `--project` (refuse them with a message naming the configuration), keep
> `published.json` for resumption, and refuse a folder already published to another repository
> than the configured one (`this folder was published to <repo>, not <configured repo>`).

## Automated tests

- `Category=Unit`: no `config.json` → error naming `jidota init`, no `gh` call.
- `Category=Unit`, fake `gh`: a folder with a spec and 3 tickets gives the issue titles, sub-issue
  links and Project adds of the golden run; `published.json` and the updated files match golden
  files.
- `Category=Unit`: failure after ticket 2 then re-run creates only ticket 3.
- `Category=Unit`: `--repo` is refused; a mismatching `published.json` repository is refused.
- `Category=Unit`: a spec with no `(scope)` item exits 2.

## How to verify

`jidota spec publish specs/<slug> --dry-run` on a test spec lists what would be created, with the
configured destination.

## Acceptance criteria

- [ ] The destination is always the jidota configuration; no config → error before any read
- [ ] A partial publication resumes without duplicates
- [ ] Titles, sub-issue links, Project adds and file updates match the Python script
- [ ] The chosen reading of the contradiction is recorded in ARCHITECTURE.md
