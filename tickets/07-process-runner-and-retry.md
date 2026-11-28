# 07 — Process runner and retry policy

**Depends on:** 03
**Reference:** ARCHITECTURE.md §2 (External tools through their CLIs, behind an interface), §2.2
(Processes, Resilience), §7.1 (Retry), §9.2 (Shell injection)

## Goal

One component in `Hosts/` that starts every external CLI (`git`, `gh`, `az`, `docker`) with an
argument list, captures its output, kills it with its whole tree, and retries what the retry table
allows. Every host ticket builds on it.

## Job to do

1. `IProcessRunner`: run an executable with `ProcessStartInfo.ArgumentList` (never a shell string,
   never `UseShellExecute`), a working directory, optional environment, a timeout; return exit
   code, stdout, stderr. Kill on timeout or cancellation with `Process.Kill(entireProcessTree: true)`.
   Values from tickets never reach a shell (§9.2).
2. Executable lookup on `PATH`; a missing executable is an error naming it (`'gh' not found on PATH`).
3. Log every command at `Debug` with its arguments only (ticket 03).
4. Retry with Polly, applied by the host methods that make network calls:

   | Failure | Behaviour |
   |---|---|
   | network error, timeout, HTTP 5xx, GitHub rate limit | 3 attempts, increasing delay |
   | HTTP 401, 403, 404 | never retried: access does not come back by retrying |
   | any other non-zero exit | not retried |

   After the last attempt the caller decides by action (poll skipped, Status write redone at the
   next poll, push or PR creation → needs-human): this ticket returns a typed failure
   (`Transient`, `AccessDenied`, `NotFound`, `Failed`) and the message, nothing more.

> The architecture does not say how a 5xx or a 401 is recognised in a CLI's output. Classify from
> stderr (`HTTP 5\d\d`, `HTTP 401`, `HTTP 403`, `HTTP 404`, `rate limit`, timeouts for `gh`; the
> error text of `az`), with the patterns in one table, and add a fixture per pattern.

## Automated tests

- `Category=Unit`, with a fake runner (NSubstitute): a transient failure twice then success gives
  3 calls and success; a 401 gives 1 call and `AccessDenied`; a 404 gives `NotFound`.
- `Category=Integration`: start `dotnet` (always present) with an argument holding spaces, quotes
  and `;`: it arrives as one argument, unchanged.
- `Category=Integration`: a child that starts a grandchild and sleeps is killed with its tree on
  timeout (no process left).
- `Category=Unit`: one test per stderr classification pattern, from recorded samples.

## How to verify

`dotnet test --filter FullyQualifiedName~ProcessRunner`.

## Acceptance criteria

- [ ] No call uses a shell or `UseShellExecute`
- [ ] Arguments with spaces, quotes and shell characters arrive unchanged
- [ ] Timeout and cancellation kill the whole process tree
- [ ] 3 attempts on transient failures; 401, 403 and 404 are never retried
- [ ] Commands are logged with arguments only, never with their output
