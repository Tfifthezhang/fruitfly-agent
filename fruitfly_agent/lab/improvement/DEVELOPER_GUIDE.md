# Develop Independent Improvement Stages

[Up: Improvement](README.md)

Improvement executes one explicitly requested stage per invocation. Its public
entry does not run a baseline, organizer, editor and candidate execution together.
No stage may call another research stage to fill missing inputs.

## Validate in a new environment

Run the following from the source checkout. Python 3.11+ is supported by the
package; Harbor benchmark execution requires its documented Linux runtime.
Installation downloads dependencies. It starts no model or task containers.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
# Optional: install only when using benchmark adapters (network download).
.venv/bin/python -m pip install -e '.[benchmarks]'
```

First verify the offline contracts. Fake Providers prove wiring and rejection
behavior, not model quality or connectivity:

```bash
.venv/bin/python -m fruitfly_agent --help
.venv/bin/python -m unittest tests.run.test_research_configuration tests.experiments.test_stage_cli tests.lab.test_organizer tests.lab.test_evidence_index
.venv/bin/python -m unittest discover -s tests -t .
# Optional Eval catalog discovery; probes local prerequisites, starts no containers/models.
.venv/bin/python -m fruitfly_eval catalog --json
```

Use a separate workspace. `/absolute/path/to/...` below is a placeholder; replace
it with your checkout or existing workspace. Keep this executable path when the
workspace is outside the checkout:

```bash
LAB=/absolute/path/to/checkout/.venv/bin/fruitfly-agent-lab
WORKSPACE=/absolute/path/to/workspace
# Create WORKSPACE yourself before init. Existing files are never overwritten.
"$LAB" --cwd "$WORKSPACE" init
```

Plain init supplies the system/model configuration, not a task backend. Copy the
[research example](../../../examples/experiments/research-stage.example.yaml) to
`WORKSPACE/.fruitfly/improvement.yaml`. Set `baseline.config` to the generated
`./default-config.yaml` and `baseline.profile` to `baseline`. For an existing daily
profile, reference its actual config and profile instead. Review `models.roles`
in that system file and the shared model catalog. Set key values only in the
workspace secret environment or process environment; never put them in research
YAML, commands, reports or component documents.

Inspect before any model execution:

```bash
"$LAB" --cwd "$WORKSPACE" improvement show
"$LAB" --cwd "$WORKSPACE" improvement check
"$LAB" --cwd "$WORKSPACE" improvement defaults
```

Import check returns exit 3 when its selected source is missing; replace the
placeholder rather than running the stage. A valid preview does not prove a
Provider endpoint or Docker environment is reachable. A missing future-stage
alias is allowed until that stage is selected.

## Import and inspect retained records

For historical diagnosis, no Docker/preparation/model access is required. In
`stages.import`, set `source: eval` and `path` to the completed archive; use
`source: batch` for an existing public `ResearchBatch` JSON. Select a unique
`publish_as`, then set `next.stage: import`.

```bash
"$LAB" --cwd "$WORKSPACE" improvement check
"$LAB" --cwd "$WORKSPACE" improvement step
"$LAB" --cwd "$WORKSPACE" improvement list
"$LAB" --cwd "$WORKSPACE" improvement inspect
```

The step result returns `run_id`, `bundle`, `report` and publication information.
Use that exact run ID for `improvement report RUN_ID`. Check `batch.json` for task,
execution and observation counts. Official rewards are observations, distinct from
execution status. Error records can retain a nonzero raw reward. Missing usage,
termination diagnostics and historical learning state stay unknown. Preserve the
original Eval archive for any deep reads not included in the imported grant.

Read the compact import outputs before opening individual trajectories:

| Output resource | What to check |
|---|---|
| `overview.json` | Task/execution counts, execution statuses and supplied observation names |
| `executions.json` | Per-run status, official observations, termination source and available time |
| `coverage.json` | Directory coverage, observation availability and terminal-source coverage |
| `batch.json` | Authoritative tasks, receipts, observations and artifact identities |

The stage report's output resources locate these immutable blobs; do not assume
their logical names are workspace file paths. Inside Organizer and Editor, the
three compact views are granted under `context/`. Per-run evidence uses
`context/executions/<run-id>/` in both roles. Directory completeness does not prove
original trajectories were read. `not_supplied` means that no observation was
supplied for that record; it cannot establish that an observation never existed.

Select organize only when a reading guide is useful. Configure
`stages.organize.inputs.batches` with the imported alias, then set
`next.stage: organize`. Inspect its guide and declared coverage before relying on
it. Organization may sample records; accepted output does not certify complete
reading. Both organize and propose expose official observations separately.

For proposal, configure `stages.propose.inputs.batches`; evidence and assessments
are optional. Set its direction, field grants, allowance and a new output alias.
Set `next.stage: propose`, inspect `show` and `defaults`, then run `step` explicitly.
Organize/propose make model requests and may incur charges. Current research roles
use evidence tools; enabling daily Subagent alone does not add delegation to these
roles. Inspect the supplied tools and retained role records rather than assuming
that reading has been parallelized.

When checking efficiency, compare the same selected inputs and grants. Read
stage wall time separately from per-request/operation times. Inspect evidence
supply receipts for returned characters, responses and source spans. One search
response can contain multiple exact source spans; it consumes one response and
all returned characters. Format repair preserves previously granted material,
recorded citations and the remaining shared allowance. More calls or a successful
submission do not establish deeper reading or a better candidate.

Inspect the complete candidate under `candidates/<run>/<candidate-id>/`:
`baseline/config.yaml`, `candidate/config.yaml`, `changes.json`, `rationale.json`
and `total-changes.json`. Verify each change's evidence, parameter semantics,
expected effect and disconfirming conditions. A valid candidate is not an executed
or independently verified improvement. A proposal may legitimately retain baseline.

## Prepare and execute a benchmark comparison

This path requires the optional benchmark dependencies, Docker, task access,
credentials and a prepared Linux Agent runtime. Preparation can download/build/start
containers; task execution additionally makes model requests and incurs charges.
Follow the [server guide](../../../fruitfly_eval/SERVER_GUIDE.md) for host mounts,
architecture and environment setup.

In a new, empty benchmark workspace, initialize the registered task collection:

```bash
"$LAB" --cwd "$WORKSPACE" init --source task-set --benchmark terminal-bench-4
```

This writes a research-shaped `experiment.yaml`, tasks, Eval request and host
inputs. Configure the generated system/model files and `eval-host.yaml` first.
Use its explicit path for preparation. Copy it to `improvement.yaml` when using
the normal Improvement entry; do not overwrite an existing authored study.

```bash
"$LAB" --cwd "$WORKSPACE" eval prepare --config .fruitfly/experiment.yaml --tasks-only
"$LAB" --cwd "$WORKSPACE" eval prepare --config .fruitfly/experiment.yaml
"$LAB" --cwd "$WORKSPACE" improvement check --config .fruitfly/experiment.yaml
```

Prepared material must match current source and declared runtime resources. Run
prepare again after relevant source/configuration changes; do not disable identity
checks. Preparation is separate from the explicit stage execution.

For a controlled comparison, execute baseline and candidate as separate invocations:

| Invocation | `stages.execute.inputs.harness` | Example output alias |
|---|---|---|
| Baseline | `{config: ./default-config.yaml}` | `baseline-results` |
| Candidate | `{candidate: candidate-a}` | `candidate-a-results` |

Use the same task document, model/runtime conditions, attempts and initial state
policy. Run `show`, `check`, then `step` for each explicit selection. Importing an
old result does not establish that it is a comparable fresh baseline. Follow
[learning-state rules](../../../AGENTS.md#follow-the-detailed-workflow-when-needed)
when retained state participates. Execute requires runnable task material, not
just archived result records.

Configure `stages.compare.inputs.batches` with the two result aliases, give it a
new output alias, and set `next.stage: compare`. Run `show`, `check`, then `step`.
Comparison may make model requests. Review official outcomes, reliability, cost
coverage and hypothesis checks separately. Comparison neither activates the
candidate nor automatically selects another stage.

## Recover or diagnose a stopped stage

| Observation | Action |
|---|---|
| Unknown input alias | Inspect `references.json`; select an explicit available producer |
| Missing original bytes | Consult reading-scope/coverage; explicitly supplement permitted path/hash pairs |
| Evidence supply exhausted | Inspect supplied ranges; revise stage allowance or narrow the task |
| Context budget rejected | Reduce material per invocation; preserve an output reserve |
| Invalid candidate | Inspect field validation and role repair events; fix the supported cause |
| Failed known attempt | Keep its report; choose a new explicit invocation as appropriate |
| Unresolved attempt | Inspect effects first; `attempt: retry-unresolved` explicitly permits another attempt |
| Alias collision | Keep retained result; use a new alias for different output |
| Prepared material mismatch | Prepare current declared source/runtime material again |

`inspect` and `resume` inspect durable state; neither replays model/tool effects.
`attempt: reuse` can reuse identical completed work. `fresh` does not authorize
replaying unresolved work. Neither cancellation nor retry rolls back filesystem
or remote effects. Run reports and immutable producer snapshots remain the
source of truth. Output history never edits the authored research YAML.

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

`show` resolves only the selected stage's references and reports its role, external
effects, controls and edit grants. `check` performs offline admission, not a model
connectivity or benchmark-quality check. Model/task work requires explicit `step`.

## Keep intent separate from historical observations

| Section | Owner and meaning |
|---|---|
| `research` | Identity, title, output root and branch |
| `baseline` | Complete system config and optional profile |
| `stages.<name>.inputs`, `context` | Explicit input artifacts and supplementary material |
| `stages.<name>.allowance` | Independent time and evidence supply limits |
| `stages.propose.optimization` | Owner-validated field grants |
| `stages.<name>.publish_as`, `attempt` | Output name and reuse/retry policy |
| `next.stage` | Exactly one stage to execute |

Every relative path resolves from this document. All stage syntax is validated;
unselected stages do not resolve future output references or require credentials.
Models bind only in system `models.roles`. Algorithm instructions/defaults live in
their H/S/I owner documents. Ordinary customization preserves component references;
candidate exports freeze complete effective contents. There is no second profile
override grammar in the research document.

Execution never rewrites authored YAML. History is available in
`configuration/observed.json`, `configuration/current.md`, run reports and
`references.json` under the output root. Editing these projections does not select
or authorize work. Run `show` after changing the research document.

## Bind named inputs

```yaml
stages:
  propose:
    inputs:
      harness: {candidate: candidate-a}
      batches: [{artifact: candidate-a-results}]
      evidence: [{artifact: candidate-a-evidence}]
      assessments: []
    context: []
    direction: Improve supported behavior and state disconfirming observations.
    allowance:
      seconds: 1200
      evidence_characters: 256000
      evidence_responses: 64
    optimization:
      scope: defaults
      include: {}
      exclude: []
    publish_as: candidate-b
    attempt: reuse
next:
  stage: propose
```

`artifact` resolves a branch-local named bundle. `candidate` selects a complete
exported candidate. `bundle` is an explicit portable bundle path. `config` selects
a complete system file for a harness. No latest/score/directory ordering selects
inputs. A different output needs a different alias.

| Stage | Required material | Output |
|---|---|---|
| `import` | Source kind and retained path | Batch, official observations and provenance |
| `eval` | Fixed config, tasks and prepared backend | Execution batch |
| `organize` | Batches | Reading guide and sources |
| `assess` | Batches; optional evidence/context | Structured diagnostic feedback |
| `propose` | Batches; optional harness/evidence/feedback | Complete candidate or empty proposal |
| `execute` | Explicit harness and executable tasks | New execution batch |
| `compare` | At least two batches | Attributable comparison |

Organization is optional. Organize and propose receive batch observations as
`context/extensions/observations.json`; execution status and reward stay distinct.
Providing a resource does not prove the model read it. Guides remain derived
text; check coverage and original spans before attributing causes.

## Derive a candidate from the selected complete system

Resolution starts from baseline or an explicitly selected complete candidate.
Customize a separate system profile/component file and select it with `config`
when making human adjustments. Preserve the original export. Model modifications
remain isolated, owner-validated and independently recorded. Unchanged components
survive materialization. Research selection does not authorize activation.

`stages.propose.optimization.scope` is `defaults` or `explicit`. Include grants
replace an owner's fields; exclude removes owners. Defaults include enabled
supported components except File memory and the three I instruction roles.
Disabled components stay disabled. Protected and mode-dependent owner validation
still applies. I grants do not create an independent I comparison backend.

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

## Find the implementation and its checks

| Change | Implementation owner | Offline checks |
|---|---|---|
| Stage names, exposed controls, roles and effects | `stages/registry.py` | `tests.run.test_research_configuration`, `tests.improvement.test_stage_contracts` |
| Research YAML validation and selected-stage projection | `../../run/improvement/configuration/document.py` | `tests.run.test_research_configuration` |
| Input binding and output-only configuration history | `../../run/improvement/context.py`, `../../run/improvement/configuration/presentation.py` | `tests.experiments.test_stage_cli`, `tests.experiments.test_research_continuation` |
| Historical Eval conversion and official observations | `../../../fruitfly_eval/improvement/` | `tests.eval.test_reading_materials` |
| Compact shared views, retrieval and supply accounting | `evidence/` | `tests.lab.test_research_grants`, `tests.lab.test_evidence_index` |
| Reading-guide generation | `organizer/` | `tests.lab.test_organizer` |
| Detached proposal, validation and repair | `editor/`, `evidence/__init__.py` | `tests.lab.test_detached_editor`, `tests.lab.test_editor_execution` |
| CLI defaults and new-workspace inputs | `../../experiments/`, `../../../examples/experiments/` | `tests.experiments.test_scaffolding`, `tests.experiments.test_stage_cli` |

Paths in this table are relative to this guide's directory. Register controls in
`stage_definitions()` and expose them through the existing public Lab API; the
research parser consumes that declaration. Bind stage behavior through the stage
handler contract or injected external stages. Do not add a second configuration
registry or a new runtime loop. Update the owning configuration guide, examples
and rejection tests whenever a public control changes.

For a selectable method, follow [Lab admission](../README.md#develop-an-algorithm)
and [Catalog configuration](../catalog/CONFIGURATION.md): declare owner defaults,
model dependencies, editable/protected fields and frozen resources. Prove an
allowed candidate changes actual isolated execution, a forbidden edit fails,
and source configuration remains intact. Research field grants authorize only
already declared owner surfaces.

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
