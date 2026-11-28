# 28 — Global pause on quota and auth

**Depends on:** 15, 23
**Reference:** ARCHITECTURE.md §7.1 (Agent run: quota, `claude` session expired), §8.2, §8.3 (Quota
retry, Quota warning threshold); feature "JidoTa operated from one command"

## Goal

Stop starting agent runs when the subscription limit is reached or the `claude` session has
expired, and start again when it is safe, without sending jobs to a human.

## Job to do

1. **Quota** (`rate_limit_event` with `rate_limit_info.status: rejected`, run ended `quota`):
   - global pause: no run starts; running runs are not stopped; every job stays at its stage
     (not needs-human);
   - resume on its own at `resetsAt`, or every 30 min when the event gives no time;
   - the run that hit the limit is started again after the pause (not counted as a failure).
2. **Auth** (run ended `auth`): global pause until `jidota resume` (ticket 31/32), after a new
   `claude` sign-in. No automatic retry.
3. **Warning** (`allowed_warning`, with `utilization`): shown on the dashboard; when `config.json`
   has a threshold and `utilization` is above it, no new run starts until the next event below it.
4. State visible to `jidota status` and `GET /api/status`: `paused: quota` (with the resume time),
   `paused: auth`, or running.
5. Log `Information` at pause and resume.

> The unit of `resetsAt` comes from the answer recorded in ticket 02's fixture README.
> The warning threshold is **Not decided** (§8.3): with no value in `config.json`, warnings are only
> shown.

## Automated tests

`Category=Unit`, clock injected:

- `rate-limit` rejected with `resetsAt` = now + 10 min → paused; at +9 min still paused; at +10 min
  running; the cut run is started again.
- Rejected without `resetsAt` → retry every 30 min.
- `auth` → paused until resume is called; the clock alone never resumes.
- Warning above a configured threshold → no new run; below → runs start; no threshold → no effect.
- Jobs keep their stage during a pause (none goes to needs-human).

## How to verify

`dotnet test --filter FullyQualifiedName~Pause`.

## Acceptance criteria

- [ ] A quota rejection pauses every new run and resumes at `resetsAt` (else every 30 min)
- [ ] An auth failure pauses until `jidota resume`
- [ ] No job goes to needs-human because of quota or auth
- [ ] The pause state and resume time are visible in the status
