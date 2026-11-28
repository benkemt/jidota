# 16 — Fake `claude` executable for tests

**Depends on:** 02
**Reference:** ARCHITECTURE.md §2 (External tools … behind an interface), §2.2 (End-to-end without
tokens)

## Goal

A test executable that stands in for `claude`: it replays a recorded `stream-json` file and writes
the job file an agent would write, so the job loop can be tested end to end in a pipeline without
tokens.

## Job to do

1. A small console project `tests/FakeClaude/`, built with the tests and copied to the test output.
2. Behaviour, driven by a scenario file named in an environment variable (`FAKE_CLAUDE_SCENARIO`):

   ```json
   {
     "stdout": "Fixtures/stream-json/finished.jsonl",
     "lineDelayMs": 0,
     "writeFiles": [{ "path": "{jobFolder}/build.md", "content": "STATUS: DONE\n\n# Build — {jobId}\n" }],
     "commit": true,
     "exitCode": 0,
     "hang": false
   }
   ```

   - prints the lines of `stdout`, with the delay between lines;
   - writes each file of `writeFiles` (placeholders taken from the prompt argument: `Job folder:`,
     `Round folder:`, `Worktree:`);
   - with `commit`, adds a change and a commit in the worktree, as a builder does;
   - `hang: true` sleeps until killed (timeout and cancel tests);
   - exits with `exitCode`.
3. It writes its own argv and working directory to `<scenario>.argv.json`, so tests can assert the
   exact command line of ticket 18.
4. Scenarios can be a list consumed in order (build, then reviewers, then approver), one per call.

## Automated tests

- `Category=Integration`: running FakeClaude with the `finished` scenario prints the fixture
  unchanged and writes `build.md` with `STATUS: DONE`.
- `Category=Integration`: `hang` is killed by a 1-second timeout of the process runner (ticket 07).
- `Category=Integration`: argv recording holds every argument as passed.

## How to verify

`dotnet test --filter FullyQualifiedName~FakeClaude`.

## Acceptance criteria

- [ ] FakeClaude replays a fixture byte for byte
- [ ] It writes the job files and commit a scenario asks for
- [ ] It records its argv and working directory
- [ ] It can hang until killed
- [ ] It needs no network and no Claude account
