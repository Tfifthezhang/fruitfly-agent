# Improve Improvement Components

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

Candidate I changes editor or evaluator prompts through registered configuration.
All six editor prompts and three evaluator prompts are eligible under explicit
grants. Each role uses an independent invocation time. Schemas,
permissions, independent objectives, thresholds and private material stay fixed.
Inner search cannot edit I. Each episode has fresh H/S and frozen experience.
Exact adopted source bytes survive restoration and recovery.

[Evaluator comparison](methods/evaluator_comparison/README.md) installs candidate
prompts into this same episode runner. Private checks use the frozen outer
reference policy; candidate judgments cannot verify their own adoption.

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

Use the [experiment CLI](../../../experiments/README.md) with a referenced task
document containing `source: editor` and `material: editor-study`. Grant the selected
I fields in experiment `edit`. The [editor recipe](../../../../examples/experiments/editor.example.yaml)
selects measured feedback and independent phase times. Run `improvement check`, then explicitly
`improvement run` or `rsi run`; real requests may incur charges. Public embedding
requests remain available below.

| Parameter | Default | Meaning |
|---|---|---|
| `inner_strategy` | `harness2` in embeddings; `simple` in CLI | Registered inner search schedule |
| `inner_components` | `base_prompt` | Space-separated registered H/S IDs; must be runnable in the file environment |
| `repetitions` | 2 | Independent fresh episodes per package, 2–10 |
| `inner_depth` | 1 | Sequential inner search depth, 1–3 |
| `min_gain` | 0 | Candidate paired mean gain must strictly exceed this value |
| `max_regression` | 0 | Allowed per-case and paired regression |

Phase times come from the outer `RunPlan.timeouts`; each editor, leaf execution and evaluator starts its own clock. Repetitions and fixed depth define the study, while usage is observed without model/execution quotas. Incomplete evidence cannot pass verification.

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

These are finite-sample rules, not a statistical confidence certificate. Providers
may be stochastic and may not expose seeds. No claim of universal nonregression
or published capability gains follows from passing this policy.

## Preserve isolation and lifecycle

Each episode creates fresh component adapters, generator/editor state, history
and file workspace. Both branches start from the same H/S and experience. Inner
experience has no production writer. H/S experiment artifacts are never activated
by adopting I. The experiment uses Lab directly, not recursive Application jobs.

Every nested request and leaf execution contributes an observation to its enclosing report. There is no child quota, cost-ratio veto or aggregate I-trial deadline. User cancellation propagates; unconfirmed retirement stops further scheduling.

Persistent candidates use ordinary [host adoption](../../../run/improvement/README.md).
Only an idle Application can activate a separately prepared runtime. Startup
failure retains the old version. The [RSI driver](../../rsi/README.md) can reuse
the exact completed proof, then load the activated I for the next generation.
The independent CLI starts only explicitly. No background evolution, arbitrary
code replacement, model training or online editing is installed.

## Verify offline

```bash
.venv/bin/python -m unittest tests.lab.test_improver tests.workflows.test_editor_evolution
```

Synthetic Providers test actual prompt loading, private trials, paired checks,
timing and two-generation activation. Their designed response behavior proves
control flow only. Real quality and API behavior require explicitly authorized
integration experiments. No new secret environment variables are introduced.

Embedding hosts can supply another `EpisodeExecutor` through
`ImproverTaskRunner(..., episode_factory=...)` and register the enclosing execution
definition. The public request/result contracts keep timing, source identity and
private comparison separate from the task backend. The bundled native material catalog uses task packages. The optional
[Eval episode composition](../../../../fruitfly_eval/improvement/README.md#compare-i-on-prepared-benchmarks)
registers benchmark-backed comparisons through `comparison_definition`; Lab does
not import Eval. A task runner alone does not install an episode study.

## Keep infrastructure fixed

Research, progress, evidence access and search schedules are fixed experiment conditions. Editor and evaluator prompts are mutable I surfaces. See [experiment conditions](../../../experiments/CONFIGURATION.md).