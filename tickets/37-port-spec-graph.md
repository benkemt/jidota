# 37 — Port `ticket_graph.py` to `jidota spec graph`

**Depends on:** 05
**Reference:** ARCHITECTURE.md §2.1 (Graph/ — GraphNet is the base of Spec/ graph), §4 (Spec/), §6
(Commands, Compatibility), §12 (Invariant 12)

## Goal

The spec factory checks the ticket graph through `jidota`, reusing the .NET implementation that
already exists in `Graph/GraphNet`, with the output of `ticket_graph.py`.

## Job to do

1. Move the logic of `Graph/GraphNet` (`Graph.cs`, `Ticket.cs`) into `Spec/` (YamlDotNet already
   used there), and expose:

   ```
   jidota spec graph <folder>                     # graph + waves + frontier
   jidota spec graph <folder> --merged T1         # frontier once T1 is merged
   jidota spec graph <folder> --in-progress T2    # ids in progress, comma-separated
   jidota spec graph <folder> --mermaid           # Mermaid diagram
   jidota spec graph <folder> --json              # machine output
   ```

2. Exit codes: 0 valid graph, 2 invalid graph (cycle, unknown reference…).
3. Output identical to `ticket_graph.py` (the README of `Graph/` states the two implementations
   give identical output); keep the messages as they are.
4. `Graph/PyGraph` stays as the prototype (features, "Documents to align").

## Automated tests

- `Category=Unit`: on `Graph/tickets/` (T1–T5), the default, `--merged`, `--mermaid` and `--json`
  outputs equal golden files recorded from `ticket_graph.py`.
- `Category=Unit`: a cycle and an unknown `depends_on` exit 2 with the Python message.
- `Category=Unit`: `--in-progress` removes those ids from the frontier.

## How to verify

`jidota spec graph Graph/tickets --json` and `python Graph/PyGraph/ticket_graph.py Graph/tickets
--json` give the same JSON.

## Acceptance criteria

- [ ] Same arguments, outputs and exit codes as `ticket_graph.py`
- [ ] The code comes from `Graph/GraphNet`, not a third implementation
- [ ] Parity tests run in the pipeline without Python
