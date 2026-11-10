# Experiment Files

[Up: Examples](../README.md)

Use one research main file to inspect prior activity and select one next stage.
See the [field guide](../../fruitfly_agent/experiments/CONFIGURATION.md) and
[developer guide](../../fruitfly_agent/lab/improvement/DEVELOPER_GUIDE.md).

| Recipe | Required material |
|---|---|
| [Independent research](research-stage.example.yaml) | Replace historical source paths; model stages need credentials |
| [Default optimization scope](improvement-defaults.example.yaml) | Offline preview or explicit portable batch inputs |
| [Benchmark batch](benchmark-smoke.example.yaml) | Prepared [collection](tasks/tb4-smoke.yaml); executes only the selected complete config |
| [Explicit prompt grant](benchmark.example.yaml) | Fixed projection with a prepared collection |
| [Multiple collections](multi-task.example.yaml) | Prepared [request/host references](tasks/multi.yaml) |
| [TB4 request](tb4-smoke-request.example.json) | [Linux setup](TB4_SERVER.md) |

## Initialize and prepare

```bash
fruitfly-agent-lab init --source task-set --benchmark terminal-bench-4
# Configure model aliases, private credentials and Linux host paths first.
fruitfly-agent-lab eval prepare --tasks-only
fruitfly-agent-lab eval prepare
fruitfly-agent-lab improvement show
fruitfly-agent-lab improvement check
# Executes exactly next.stage; model/task work incurs charges.
fruitfly-agent-lab improvement step
```

Initialization makes no external request. Preparation may download/build/start
containers, without task model calls. The generated main file initially selects
fixed baseline execution. After completion, edit `next` to organize its batch,
assess observations or generate a candidate. No command schedules these stages
on your behalf. Plain `init` creates only system/model/secret files; copy the
research example for a history-only study.

## Continue from existing outputs

```yaml
stages:
  propose:
    publish_as: candidate-b
    inputs:
      harness: {candidate: candidate-a}
      batches: [{artifact: candidate-a-results}]
      evidence: [{artifact: candidate-a-evidence}]
next:
  stage: propose
```

Names refer to outputs in the selected branch. A complete candidate is inherited
before owner-validated Editor changes. Human adjustments use a separately
selected complete system configuration. Optional evidence and
feedback do not require rerunning the organizer/assessor. No score is required.
Each invocation retains its configuration and differences; output-only history summarizes recent activity without rewriting authored YAML.

The system file still owns H/S/I and shared model definitions. `models.roles` selects
stage aliases in that system profile. Credentials stay outside configuration/report
files. Paths resolve from their declaring document. Generic file tasks need an
explicit registered backend; they do not install a local task executor.
