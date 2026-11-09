# Develop Independent Improvement Stages

[Up: Improvement](README.md)

Improvement executes one explicitly requested stage per invocation. Its public
entry does not run a baseline, organizer, editor and candidate execution together.
No stage may call another research stage to fill missing inputs.

## Start from one research document

Copy the [stage example](../../../examples/experiments/research-stage.example.yaml).
Replace placeholder paths before execution. The system config and model catalog
use ordinary FruitFlyAgent formats. Credentials remain in the secret environment.

```bash
fruitfly-agent-lab improvement show --config experiment.yaml
fruitfly-agent-lab improvement check --config experiment.yaml
# Executes only next.stage. Model stages incur charges.
fruitfly-agent-lab improvement step --config experiment.yaml
```

`show` resolves named references and displays user intent and retained observations.
`check` validates the selected stage configuration without creating a Provider;
it does not establish connectivity or quality. Model/task execution requires an
explicit stage command or `step`.

## Keep intent separate from historical observations

| Section | Owner and meaning |
|---|---|
| `research` | User: identity, title, output root and branch |
| `baseline` | User: original system config and optional profile |
| `roles` | User: executor, organizer, assessor and editor model aliases |
| `overrides` | User: ordinary system profile changes for the next invocation |
| `optimization` | User: default/explicit editing scope, include grants and exclusions |
| `stages` | User: stage-local parameters |
| `evidence` | User: shared evidence navigation limits |
| `next` | User: exactly one stage, named inputs, context, attempt and output alias |
| `observed` | Generated: retained stage history and available branch references |

Every relative path resolves from this document. Unknown fields fail. Settings
for an unrelated stage do not require that stage's backend or credentials.
Generated observations never select inputs or override user controls. Their
update preserves authored text and refuses to overwrite concurrent file edits.
Run reports remain authoritative if a projection cannot be refreshed.
`observed.last_invocation` describes the last invocation, including its settings;
it is not a live preview of later edits. Run `show` after editing. Set
`research.history_entries` (default 10) to bound generated history and references.
The complete branch index remains in `references.json`.

## Bind named inputs

```yaml
next:
  stage: propose
  publish_as: candidate-b
  inputs:
    harness: {candidate: candidate-a}
    batches: [{artifact: candidate-a-results}]
    evidence: [{artifact: candidate-a-evidence}]
    assessments: []
  context: []
  attempt: reuse
```

`artifact` resolves an explicitly named output in the current branch.
`candidate` selects a complete exported candidate configuration. `bundle` accepts
an explicit portable bundle path. No global latest, score ordering or directory
ordering selects the next candidate. A different result needs a different output
alias; candidate IDs are also registered as branch references.

| Stage | Required inputs | Output |
|---|---|---|
| `import` | Source kind and retained path | Research batch and original provenance |
| `eval` | Fixed config, task source and prepared Eval backend | Execution batch with official observations |
| `organize` | One or more batches | Reading guide, source links and coverage |
| `assess` | Batches; optional evidence/context | Structured feedback attached to retained records |
| `propose` | Batches; optional candidate, evidence and feedback | Complete candidate export or empty proposal |
| `execute` | Explicit candidate/config selection and task source | Execution batch |
| `compare` | At least two batches | Multidimensional comparison report |

Organization improves readability and traceability. Editor discovers optimization
signals and proposes changes. Assessment supplies judgments with source evidence.
Comparison does not activate candidates or choose the next research branch.
Missing official scores do not block any otherwise valid stage.

## Derive a candidate from the selected complete system

Resolution starts from the original baseline or explicitly selected candidate.
Apply human profile overrides, validate through Catalog, then resolve edit grants.
Editor changes form another independently recorded difference. Materialization
exports a complete config and resources, preserving unchanged components.
A subsequent proposal can consume that export without the original artifact cache.

Mappings in `overrides` merge recursively; lists and scalars replace. The payload
uses existing profile syntax (`models`, `H`, `S`, `I`), not a second component
language. Derived configs are retained separately. Original configs, candidates
and historical execution snapshots remain immutable.
`roles.executor` is materialized into the selected system profile. Auxiliary model
aliases do not constrain later task execution. For a research stage, current
configuration and workspace replace declarations in a historical Eval request;
reports retain the original request, its hash, effective runtime and differences.
This does not rewrite the original request or require its old paths to exist.

```yaml
optimization:
  scope: defaults
  include:
    bash-tool:
      fields: [parameters.instructions.description]
  exclude: []
```

Default scope includes enabled supported owners except `file-memory` and the
three I roles. Retained memory/skill libraries remain included. Include grants
replace the selected owner's field scope; exclusions remove owners. Explicit
scope starts empty. Disabled mechanisms stay disabled, and protected fields and
mode-dependent owner validation still apply. I proposal grants do not install an
independent I execution/comparison backend.

## Own each layer's responsibility

| Layer | Responsibility |
|---|---|
| Improvement contracts | Typed materials, named inputs, immutable activities and outputs |
| Improvement stages | One-activity lifecycle, clocks, cancellation, reuse and recovery |
| Lab | Organizer, Editor, Assessor, evidence access, candidate validation and executable target adapters |
| Run | Configuration resolution, role construction, storage and complete candidate export |
| Experiments | Thin CLI composition and optional Eval adapter wiring |
| Eval | Benchmark preparation, execution, official observations and history conversion |

Do not import Experiments from Run/Lab or Eval from the Improvement runtime.
`ProposalStage` has generators, components and candidate validation; it has no
runner, selector or search controller. Historical proposals consume retained
records directly, without fabricating trial scores or search evaluations.
`StageInputs` names harness, batches, evidence, assessments and context. Bind
these names before dispatch rather than deriving roles from argument positions.

## Construct only the requested model role

`ResearchRoles` loads one shared model catalog. The selected stage constructs its
own Provider only after configuration capture. Organizer/Assessor/Editor have
independent clocks and instruction components. Execution uses its registered task
backend; it does not start an Editor or synthesize new candidate modifications.

Feedback submission uses the existing strict assessment receiver. Retain invalid
or unavailable feedback explicitly; never publish invalid prose as accepted
structured feedback. Such unavailability does not erase the execution batch or
prevent later organization/proposal.

## Persist before external effects

Each invocation captures requested and effective configuration, source receipts
and informational differences before Provider calls or task execution. Outputs
retain producer, configuration and transitive immutable dependencies.

```text
<output-root>/
  references.json
  study.json
  research-events.jsonl
  artifacts/
  inputs/
  evidence/
  candidates/<proposal-run>/<candidate-id>/
    baseline/config.yaml
    candidate/config.yaml
    changes.json
    rationale.json
    human-changes.json
    total-changes.json
  results/
  runs/<run-id>/
    configuration/requested.yaml
    configuration/effective.json
    configuration/sources.json
    configuration/differences.json
    configuration/optimization.json
    configuration/optimization.md
    inputs.json
    outputs.json
    report.json
    report.md
```

Optimization tables exist for proposal work. Reports distinguish failed,
interrupted and completed invocations. Historical producer configurations remain
attached even if the current model or profile differs. Unknown historical settings
remain unknown; current settings must not be relabeled as historical facts.

## Handle repeated and interrupted work

`attempt: reuse` permits reuse of an identical completed activity.
`fresh` requests another attempt. `retry-unresolved` explicitly authorizes a new
attempt after uncertain external work. Merely changing configuration does not
invalidate historical inputs or require restarting the study.

A lost process may leave an unresolved intent. Inspect and reconcile it before
paid replay. Missing or corrupt required artifacts block only the affected stage.
Ordinary configuration differences are reported rather than treated as restore
gates. Candidate research selection is independent of production activation.

## Verify public stage behavior offline

```bash
.venv/bin/python -m unittest tests.improvement.test_stage_contracts tests.run.test_research_configuration tests.experiments.test_stage_cli tests.experiments.test_research_continuation
```

Use fake Providers and isolated artifact stores. Verify that a stage does not call
another role, that changed configuration can consume old outputs, and that a
candidate inherits the selected parent's unchanged values. Test concurrent edits,
branch ambiguity, interrupted effects, feedback rejection and complete exported
resource loading. Offline tests do not establish model quality or benchmark gains.

## Read compact benchmark materials

Import an Eval archive, then select assess or propose directly. Model organize is
optional; offline extraction has already supplied task, outcome, one reading
trajectory, execution facts and source navigation. Original files stay in Eval.
Use [import settings](../../experiments/CONFIGURATION.md#configure-stage-settings)
to select tasks or supplement exact archive-relative paths with recorded hashes.
The new import is immutable; earlier batch bundles remain valid and unchanged.
See [evidence limits](evidence/README.md#bound-an-investigation).
