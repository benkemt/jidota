# 01 — Solution scaffold and test conventions

**Depends on:** —
**Reference:** ARCHITECTURE.md §2.1 (Architecture style), §2.2 (Cross-cutting libraries), §4 (Components)

## Goal

Create the `jidota` solution, the empty module folders and the test project, so every later ticket
has a place for its code and its tests, and the whole suite runs with one `dotnet test` in a
pipeline.

## Job to do

1. Create at the repository root:

   ```
   jidota.sln
   src/Jidota/            net10.0, OutputType Exe, PackAsTool, ToolCommandName jidota
     Cli/ Web/ Poller/ Jobs/ Agents/ Recording/ Hosts/ Spec/ BranchToPr/ WorkItems/ Data/
     Program.cs
   tests/Jidota.Tests/    xUnit, NSubstitute, Testcontainers (PostgreSQL), bUnit
   ```

   `ImplicitUsings` and `Nullable` enabled, as in `Graph/GraphNet/GraphNet.csproj`.
2. `Program.cs`: a `System.CommandLine` root command `jidota` with no subcommand yet, and the
   generic host (`Microsoft.Extensions.Hosting`, built-in DI) that later tickets register into.
3. Package the plugin folder `Factory/` (agents and skills) as content of the tool, so the
   installed tool has a `plugin/` folder next to its binaries (`AppContext.BaseDirectory`). The
   agent files are read from there (§4 "One agent run").
4. Test conventions, used by every later ticket:
   - `[Trait("Category", "Unit")]`: no process, no network, no Docker.
   - `[Trait("Category", "Integration")]`: may use Docker (Testcontainers) and a real `git` on
     temporary folders; never a real `claude`, `gh` or `az`, never the network.
   - `[Trait("Category", "Manual")]`: needs a real `claude`, `gh` or `az` account; excluded from
     the pipeline (`--filter Category!=Manual`), run by hand when a ticket says so.
   - Recorded fixtures live in `tests/Jidota.Tests/Fixtures/`.
   - The pipeline command is `dotnet test jidota.sln --filter Category!=Manual`, with Docker
     available for `Category=Integration`.
5. Rule from §2.1: modules use each other through public types only; only `Hosts/` and `Agents/`
   start processes; only `Data/` holds a `DbContext`. Nothing automates it: state it in a short
   `src/Jidota/README.md` for reviewers.

> The architecture names no CI file. This ticket only makes the suite pipeline-ready; the
> pipeline definition itself is not part of this backlog.

## Automated tests

- `Category=Unit` smoke test: `jidota --help` (run in-process through the root command) exits 0
  and prints `jidota`.
- `Category=Unit` test: the plugin folder is copied to the build output and holds
  `agents/builder.md`.

## How to verify

```
dotnet build jidota.sln
dotnet test jidota.sln --filter Category=Unit
dotnet pack src/Jidota -o out && dotnet tool install --tool-path ./tool --add-source out jidota
./tool/jidota --help
```

## Acceptance criteria

- [ ] `dotnet build` and `dotnet test` succeed on Windows and Linux with no other prerequisite than
      the .NET 10 SDK (Docker only for `Category=Integration`)
- [ ] `dotnet test --filter Category=Unit` runs without Docker
- [ ] The packed tool installs and `jidota --help` exits 0
- [ ] The installed tool contains `plugin/agents/builder.md`, `security-reviewer.md`,
      `code-reviewer.md`, `approver.md`
- [ ] The module folders of §2.1 exist; no project other than `src/Jidota` and `tests/Jidota.Tests`
