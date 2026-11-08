# Improvement Examples

[Up: Examples](../README.md)

Use the [public stage ports](../../fruitfly_agent/lab/improvement/README.md#extend-a-stage)
for deterministic generators and model editors. This offline example executes
one proposal from explicitly synthetic retained records, without task execution,
model calls, network access or activation:

```bash
.venv/bin/python -m examples.improvement.offline
```

[offline.py](offline.py) injects a rule generator and component validation into
`ResearchService`. It does not run a baseline, compare outputs or schedule a
subsequent stage. Its output demonstrates contracts, not a measured quality gain.

Task packages provide optional private scoring and independent verification:

| Package | Scoring | Material |
|---|---|---|
| [Python functions](python_functions/README.md) | Restricted function tests | 8 train, 4 selection, 6 holdout |
| [Ticket triage](ticket_triage/README.md) | Normalized labels | 8 train, 4 selection, 6 holdout |

These are authored examples, not representative benchmarks. Install complete
packages in a separate workspace. The active component snapshot is the baseline;
`baseline.txt` is an optional reference. Follow [Task packages](../../fruitfly_agent/lab/improvement/tasks/README.md).

Use the [stage guide](../../fruitfly_agent/lab/improvement/DEVELOPER_GUIDE.md)
for one editable research main file, portable evidence, candidate inheritance and
separate execution. [Stage tests](../../tests/experiments/test_stage_cli.py) verify
these paths with offline Providers. No automatic nested I study is installed.
