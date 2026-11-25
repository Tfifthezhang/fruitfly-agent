# Validate selected tasks

[Up: Experiments](../README.md)

Use an initialized benchmark workspace with configured system/models and prepared
request/host files. Preparation can download/build/start containers. Execute,
organize and propose can make paid model requests. Default compare is offline.
This recipe runs one explicit stage per command, not an automatic chain.

## Freeze the task selection

Copy [tasks.yaml](tasks.yaml) into `.fruitfly/tasks/selected.yaml`. Replace both
placeholder names with exact `id` values from the prepared task receipt. Keep the
collection ID unchanged across baseline/candidate. The referenced leaf request
must use `attempts: 1` and `concurrency: 1`; the research scheduler owns repetitions.
An unknown task name fails rather than expanding to the full dataset.

In the research main file, use:

```yaml
stages:
  execute:
    tasks: {file: tasks/selected.yaml}
    attempts: 2
    concurrency: 1
    inputs:
      harness: {config: default-config.yaml}
    publish_as: baseline-selected
    attempt: reuse
    allowance: {task_seconds: 3600}
next: {stage: execute}
```

Paths above assume the main file is inside `.fruitfly/`. Keep the normal
`research` and `baseline` sections. Execute runs exactly these selected development
tasks twice, not two randomly sampled tasks. Choose repetitions before inspecting
candidate outcomes. For confirmation, use an independently selected task file.

```bash
fruitfly-agent-lab improvement show --config .fruitfly/improvement.yaml
fruitfly-agent-lab improvement check --config .fruitfly/improvement.yaml
# Explicit execution; model requests incur charges.
fruitfly-agent-lab improvement step --config .fruitfly/improvement.yaml
```

## Generate and run the candidate

Import an existing Eval batch or use `baseline-selected` directly. Optionally
organize it; propose consumes explicit batches and optional organized evidence.
Propose already edits, validates and exports a complete candidate when its decision
is a candidate. There is no separate mandatory edit stage. Inspect `decision.json`
and `proposal.json`; retain-baseline and needs-evidence decisions have no candidate.

Select execute again, changing only:

```yaml
inputs:
  harness: {candidate: candidate-a}
publish_as: candidate-selected
```

Keep the same task file, attempts and runtime conditions. Run show/check/step
again. No prior import, organize or propose is rerun. Use a new output alias when
changing configuration or requesting a fresh independent repetition.

To validate another executor model, create a complete system configuration through
normal component/model references, bind `models.roles.executor` there, and execute
with `{config: alternate-config.yaml}`. Keep model aliases out of task and research
parameters. This is a different experimental condition; record model identity,
budget and source/preparation changes. Candidate references select a frozen complete
configuration and are not a mechanism for inline model overrides.

## Compare without conversion

```yaml
stages:
  compare:
    inputs:
      batches: [{artifact: baseline-selected}, {artifact: candidate-selected}]
    publish_as: selected-comparison
    attempt: reuse
next: {stage: compare}
```

Use show/check/step. No `measured_policy`, Editor or assessor model is required.
The bundle includes `comparison.json`, `summary.md`, `metrics.csv`, `tasks.csv`.
See [metric definitions and limits](../../../fruitfly_agent/lab/improvement/assessment/methods/measured/README.md).
Missing provenance can leave the conclusion insufficient while descriptive
outcomes remain available. Review the report's mismatches and unknowns.

If retaining a full baseline and running only a candidate subset, explicitly add:

```yaml
task_scope: {artifact: candidate-selected}
```

Place it inside `stages.compare`, next to `inputs`. It must equal one input
reference. Every selected canonical task-attempt pair must exist in both plans;
attempt counts must therefore match. Different scopes without this declaration
fail; compare never silently chooses an intersection. A failed-only subset
supports recovery claims on that subset, not whole-benchmark improvement.

## Inspect interruption and verification

Completed receipts and the planned execution scope are retained in the stage
journal on interruption. A partial batch does not masquerade as a completed output
alias. Inspect durable activity before explicitly retrying unresolved external work.
There is no automatic compare, acceptance or activation after execute.

`tests.workflows.test_small_batch_comparison` exercises the production task-set
executor with three selected tasks and two attempts through offline fake ports,
then compares native results directly. Offline checks establish contracts, not
benchmark gains or external preparation health.
