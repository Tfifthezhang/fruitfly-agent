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

For fixed-depth editor experiments, prepare separate development and verification
task packages and follow [Improve editor instructions](../../fruitfly_agent/lab/improvement/improver/README.md).
That guide provides the exact experiment manifest and a `WorkflowRequest`. Preview
is offline; submitting its model-based experiment may incur charges. The
[editor evolution tests](../../tests/workflows/test_editor_evolution.py) demonstrate
actual binding and multi-generation activation with synthetic offline Providers.
