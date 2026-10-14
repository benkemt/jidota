# Linear workflow setup

Sets up the JidoTa workflow statuses (see [Workflow](../../README.md#workflow)) in a Linear team, from [`workflow.toml`](workflow.toml).

| Team status | What the script does |
|---|---|
| Missing | Creates it, with the type, color, description, and position of the file. |
| Wrong order, description, or name case | Updates it. The color you set in Linear is kept. |
| Wrong type | Linear cannot change the type of a status, so the script renames the old one `<name> (replaced)`, creates the right one, moves its issues, and archives the old one. |
| Not in the file | Only reports it. |

## Run

Python 3.11 or later, no dependency. Create a personal API key in Linear (Settings → Security & access → API) with an account that can edit the team's settings.

```
export LINEAR_API_KEY=lin_api_...          # PowerShell: $env:LINEAR_API_KEY = "lin_api_..."
python linear_workflow.py --team ABB          # dry run: shows the plan, changes nothing
python linear_workflow.py --team ABB --apply  # makes the changes
```

`--team` takes the team key, name, or ID. `--json` prints the final statuses as `name → {id, type}`, for the orchestrator's configuration. `--config` reads another statuses file.

The script can be run again at any time: when the team already matches the file, it changes nothing.

## Test

```
python -m unittest
```
