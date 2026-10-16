# Improvement Examples

[Up: Examples](../README.md)

The [offline DreamRSI replay](dream_rsi/README.md) compares policies on a synthetic tree without models.

The [offline automatic workflow](automatic_text/README.md) demonstrates model-generated learning material, original-task comparison, independent confirmation and explicit human adoption with a scripted Provider.

Task packs for the normal `/improvement` workflow. They are manually authored demonstrations, not formal benchmarks or measured improvement claims.

| Pack | Scoring | Search / independent cases |
|---|---|---|
| [Python functions](python_functions/README.md) | Restricted function-call tests | 8 train, 4 selection, 6 holdout |
| [Ticket triage](ticket_triage/README.md) | Exact normalized labels | 8 train, 4 selection, 6 holdout |

Install a complete pack into a new workspace task-packs directory. `baseline.txt` is an optional reference; the active target supplies the search baseline. Read [Task packs](../../fruitfly_agent/lab/improvement/tasks/README.md) before authoring your own.
