# src/Jidota

The `jidota` .NET tool. Its design is [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md); the work is
cut into [`../../tickets/`](../../tickets/README.md).

## Modules

A modular monolith with adapters (ARCHITECTURE.md §2.1): one project, one process, one module per
folder.

| Folder | Module |
|---|---|
| `Cli/` | commands (System.CommandLine) |
| `Web/` | local API and Blazor Server dashboard |
| `Poller/` | GitHub Project → eligible tickets, PR state |
| `Jobs/` | job state machine, scheduler (slots, touches) |
| `Agents/` | `claude -p` launch, `stream-json` reading, settings generation |
| `Recording/` | runs, tool calls, masking |
| `Hosts/` | git, GitHub (`gh`), Azure DevOps (`az`), docker |
| `Spec/` | `spec fetch \| graph \| publish` (ported spec factory scripts) |
| `BranchToPr/` | `pr collect \| open` (ported `branch_to_pr.py`) |
| `WorkItems/` | `workitems target \| check \| create` (ported `workitems.py`) |
| `Data/` | EF Core context, entities, migrations |

## Rules for reviewers

Nothing checks these automatically: every PR is reviewed against them.

- A module uses another module only through its public types.
- Only `Hosts/` and `Agents/` start a process. The external tools are reached only through their
  interfaces, so the whole loop can run in tests against fakes.
- Only `Data/` holds a `DbContext`.

## Tests

`tests/Jidota.Tests`. Every test carries a category trait:

| Category | May use | In the pipeline |
|---|---|---|
| `Unit` | nothing outside the process: no process, no network, no Docker | yes |
| `Integration` | Docker (Testcontainers) and a real `git` on temporary folders; never a real `claude`, `gh` or `az`, never the network | yes, with Docker |
| `Manual` | a real `claude`, `gh` or `az` account | no — run by hand when a ticket says so |

Pipeline command: `dotnet test jidota.slnx --filter Category!=Manual`. Recorded fixtures live in
`tests/Jidota.Tests/Fixtures/`.
