# Improve Editor Instructions

[Up: Improvement](../README.md)

Compare editors by the downstream modifications they produce. Each I trial runs
ordinary Improvement on a fresh H/S snapshot and then measures the resulting H/S
on private checks. The outer search can edit I; the inner search cannot edit I.
No component changes during an individual task execution.

## Understand the two levels

```text
Outer current editor -> propose candidate editor I'
  -> development trials of I and I'
     -> fresh initial H/S and frozen experience
     -> fixed-I inner Improvement changes declared H/S
     -> private task checks measure before/after H/S
  -> select an existing editor trial, retaining the original on measured ties
  -> final paired trials on separate verification episodes
  -> pending I candidate -> explicit adoption -> next RSI generation
```

The executed I changes `AgentEditor` instructions, not the task Agent's base
prompt. `invariant`, `domain` and `compose` are editable. `system`, `select` and
`reflect` must equal their frozen parent values. Unknown fields and changes to
component ownership fail. Loaded I snapshots preserve the exact bound source bytes,
including valid JSON formatting, so saved-default reconciliation and recovery
compare the actual adopted artifact rather than a reserialized approximation. Model, scorer, permissions, thresholds and budgets
remain outside the edit grant. I cannot be mixed with H/S in an outer job.

| File | Owns |
|---|---|
| [registration.py](registration.py) | Definition, public parameters and source preparation |
| [materials.py](materials.py) | Strict bounded manifest and disjoint task-package freezing |
| [episodes.py](episodes.py) | Fresh fixed-I inner workflow and private task checks |
| [runner.py](runner.py) | One-editor trials, attributable reports and development measurements |
| [verification.py](verification.py) | Alternating paired repeats, acceptance and immutable proof |

## Prepare independent episodes

Install at least two complete [task packages](../tasks/README.md) in the workspace:
one development package and one independent verification package. Each package
must have training, selection and holdout cases and support every selected inner
component. Keep inputs disjoint across all packages. Use the same maximizing
scorer implementation, with finite scores normalized to `[0, 1]`.

Create `.fruitfly/improvement/experiments/editor-study/experiment.json`:

```json
{
  "schema_version": 1,
  "id": "editor-study",
  "name": "Editor procedure comparison",
  "development": ["development-pack"],
  "verification": ["independent-pack"],
  "max_verifications": 1
}
```

The two pack IDs are placeholders for installed packages, not bundled examples.
Manifests require exactly these fields, are at most 16 KB, and reject duplicate
JSON keys, escaping paths and symlinks. Each partition contains 1–8 distinct
packages. Input deduplication uses NFC and trimmed whitespace; review semantic
and source-family overlap manually. The source identity includes all pack hashes,
including private material. Changing it invalidates an outstanding preview.

`max_verifications` declares 1–10 uses of the private suite. Run claims a use
durably before work; rejection, cancellation or uncertain interruption consumes
it. Claims use semantic verification material identity, independent of candidate IDs,
JSON formatting and package order. Repeated use weakens independence even when inputs are hidden; prefer
fresh suites for later research. This limit does not establish statistical validity.

## Supply the experiment inputs

Open `/improvement`, choose **Execution strategy → Editor self-improvement**,
choose the experiment under **Task**, and review **Execution parameters**.
The definition selects I, measured feedback and persistent scope by default.
Review the complete frozen preview before explicitly confirming model work.

| Parameter | Default | Meaning |
|---|---|---|
| `inner_components` | `base_prompt` | Space-separated registered H/S IDs; must be runnable in the file environment |
| `repetitions` | 2 | Independent fresh episodes per package, 2–10 |
| `inner_depth` | 1 | Sequential inner search depth, 1–3 |
| `inner_model_calls` | 12 | Shared model allowance per inner search, 4–1000 |
| `inner_executions` | 4 | Leaf executions per inner search, 4–100 |
| `evaluation_model_calls` | 1 | Reserved model allowance per private check, 1–32 |
| `max_trials` | 8 | Outer development trial limit, 1–40 |
| `min_gain` | 0 | Candidate paired mean gain must strictly exceed this value |
| `max_regression` | 0 | Allowed per-case and paired regression |
| `max_model_ratio` | 1.5 | Maximum candidate/old-editor model-call ratio |

Selecting the strategy recommends a root allowance of 512 model calls and 256
leaf task executions. Larger suites need larger budgets. Preparation calculates
a minimum that includes protected final verification; the minimum is not a
promise that every requested exploration round fits. Exhaustion rejects incomplete
evidence rather than inventing a score. Costs and tokens can remain unknown.

For a started Application, this is the equivalent request. The IDs are
placeholders; the actual `improve` operation calls models and can incur charges:

```python
from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest

request = WorkflowRequest(
    component_ids=("improvement-editor",),
    execution_id="improver-comparison",
    task_pack_id="editor-study",
    verification="scored",
    scope="persistent",
    max_model_calls=512,
    max_executions=256,
    direction="Improve proposal procedures",
    execution_parameters=(("inner_components", "base_prompt"), ("repetitions", 2)),
)
# preview = application.workflow_preview(request)  # offline
# records = await application.improve(request.direction, preview_token=preview.preview_token)
```

## Interpret measurements

Each inner search uses the episode's first training instruction. Editors see
behavior evidence and a frozen experience copy, not scorer objects or acceptance
answers. After search ends, the evaluator runs the original and selected H/S on
all train, selection and holdout cases. An unchanged H/S receives zero improvement
gain; a fresh stochastic answer alone is not a harness modification.

The outer development report contains gains, regressions, failures, usage and
evidence references. It does not grant the editor access to private answers or
verification episode instructions. Reports are generated from execution receipts,
not from an editor's self-reported score. Full inner outcomes are stored as
artifacts for human review. The private suite never enters generation or reflection.

Final validation alternates old/new execution order across repeats. It requires:

- Complete, matching reports for every declared episode and repeat.
- No failed episode or missing measurement.
- Candidate case gains and paired case differences above the regression floor.
- Paired mean improvement strictly above `min_gain`.
- Candidate model calls within `max_model_ratio` of the old editor.

These are finite-sample rules, not a statistical confidence certificate. Providers
may be stochastic and may not expose seeds. No claim of universal nonregression
or published capability gains follows from passing this policy.

## Preserve isolation and lifecycle

Each episode creates fresh component adapters, generator/editor state, history
and file workspace. Both branches start from the same H/S and experience. Inner
experience has no production writer. H/S experiment artifacts are never activated
by adopting I. The experiment uses Lab directly, not recursive Application jobs.

Every nested model request and leaf task execution spends the root ledger once.
Child allocations hold quota without reporting it as spent. Unused quota returns
on close; deadlines and cancellation propagate. An outer I trial has no additional
leaf-execution charge, and `max_trials` bounds development scheduling separately.

Persistent candidates use ordinary [host adoption](../../../run/improvement/README.md).
Only an idle Application can activate a separately prepared runtime. Startup
failure retains the old version. The [RSI driver](../../rsi/README.md) can reuse
the exact completed proof, then load the activated I for the next generation.
No autonomous background CLI, code replacement, model training or online editing
is installed.

## Verify offline

```bash
.venv/bin/python -m unittest tests.lab.test_improver tests.workflows.test_editor_evolution
```

Synthetic Providers test actual prompt loading, private trials, paired checks,
budgeting and two-generation activation. Their designed response behavior proves
control flow only. Real quality and API behavior require explicitly authorized
integration experiments. No new secret environment variables are introduced.
