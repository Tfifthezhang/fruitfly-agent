# Improvement Examples

[Up: Examples](../README.md)

Use the [public stage ports](../../fruitfly_agent/lab/improvement/README.md#extend-search)
for both deterministic generators and model editors. The complete offline workflow
example runs without keys, network or model calls:

```bash
.venv/bin/python -m examples.improvement.offline
```

[offline.py](offline.py) registers a rule generator, supplies task execution,
composition and selection capabilities, and runs the unified workflow. Its
synthetic output is a contract demonstration, not a measured quality gain.

Task packages provide optional private scoring and independent verification:

| Package | Scoring | Material |
|---|---|---|
| [Python functions](python_functions/README.md) | Restricted function tests | 8 train, 4 selection, 6 holdout |
| [Ticket triage](ticket_triage/README.md) | Normalized labels | 8 train, 4 selection, 6 holdout |

These are authored examples, not representative benchmarks. Install complete
packages in a separate workspace. The active component snapshot is the baseline;
`baseline.txt` is an optional reference. Follow [Task packages](../../fruitfly_agent/lab/improvement/tasks/README.md).
