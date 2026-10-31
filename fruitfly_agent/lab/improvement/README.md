# Improvement

[Up: Lab](../README.md)

The independent [Improvement runtime](../../improvement/README.md) owns the reliable
stage kernel. This package supplies concrete editors, algorithms, assessments,
component adapters and native execution; Run supplies persistence and activation.

Refine registered Agent components using task execution evidence. The [runtime contracts](../../improvement/contracts/README.md) separate candidate
generation, execution, composition, selection,
verification, reflection and activation. Run persists jobs; Application owns
execution and adoption. Container benchmark evaluation belongs to the separate Eval consumer.

## Follow a task

```text
Freeze plan, task, H/I/S and experience
  → execute a reference
  → propose and validate a candidate
  → execute and independently compare
  → retain an existing result
  → optionally verify a persistent change
```

| Stage | Public contract | Default |
|---|---|---|
| Materials | `TaskSource`, `TaskMaterial`, `ArtifactAccess` | Freeze explicitly selected workspace inputs as immutable bytes |
| Components | `OptimizationAdapter`, `HarnessSnapshot`, `CandidateBundle` | Object-owned text adapters; complete named file sets |
| Propose | `CandidateGenerator`, `ProposalRequest`, `ProposalResult` | Tool-using editor with a strategy-declared mission |
| Probe | `TaskRunner`, `ExecutionRecord`, `ExecutionFacts` | Detached read/write/edit file workspace with attributable facts |
| Assess | Shared model evaluator | Prompt-driven dimension, process and hypothesis judgments |
| Compose | `Composer`, `CompositionRequest` | Editor compares executions and resolves component changes |
| Select | `Selector`, `SelectionDecision` | Shared read-only per-dimension evaluator |
| Explore | `ExplorationRegistry`, `ExplorationDecision` | Continue from the official incumbent; optional process-guided seed |
| Verify | `VerificationPolicy`, optional `MeasurementSource` | Independent task-package comparison when provided |
| Reflect | `Reflector`, `ExperienceEntry` | Evidence-grounded lesson or no entry |
| Retain | `ExperienceRepository` | Host stages lessons; explicit review precedes an S library update |
| Orchestrate | `WorkflowController`, `StrategyRegistry` | Shared validation/accounting; a separately registered search schedule |

The independent [experiment CLI](../../experiments/README.md) defaults to
`simple`: one reference and one candidate per round, no composition and no
reflection. [Search strategies](strategies/README.md) keep Harness² optional.
`RunPlan` defaults to Harness²; experiment settings select their strategy explicitly.

Parallel width `k` uses `k` references, `2k` proposals, and `k` compositions when
each proposal returns one candidate. All proposals in one round receive the same
reference evidence and prior history. They cannot inspect their peers. Probes
start after the proposal pool is complete. Sequential mode performs invariant and
domain proposals and one composition per depth. By default the selected incumbent
becomes the next editing baseline. Optional process-guided exploration can choose
another completed execution as the next seed without changing the official winner.
Every composition is executed, including an unchanged one.
Generators may return no candidates or request an early stop. The built-in
`parallel` pool is independent but currently awaited sequentially. All successful
executions, including original references and probes, remain selectable.

## Separate feedback, stopping and assurance

| Decision | Rule |
|---|---|
| Propose | Task requirements, declared guidance, trajectories and optional measured feedback supply hypotheses. |
| Stop | `StopPolicy` records round limits, repeated candidates, no candidate or generator stop. Phase timeouts retain their own reasons. |
| Select | Consider original and candidate outputs. Measured selection follows declared utility. Equal official scores can use supported process comparison; unknown judgments retain the incumbent. |
| Explore | The next editing seed is a separate decision; default to the official incumbent, or use declared completed-process comparison. |
| Verify | Only an independent policy can grant `verified`; selected outputs remain `selected`. |

A phase timeout is not convergence. Unsupported or malformed comparison retains the incumbent. Each phase starts its own timer; selection has a fresh evaluator invocation. Missing references do not produce invented deliverables.

## Choose H, S or I

| Axis | Meaning | Required execution |
|---|---|---|
| H | Execution instructions and mechanisms | Compare task behavior with fixed initial S and I |
| S | Retained knowledge, skills and experience | Declare initial state, updates and reset behavior |
| I | Candidate generation and improvement instructions | Registered [editor comparison](improver/README.md); ordinary task trials reject I edits |

Component kind and H/S/I axis are independent. Existing owners expose the base
prompt, enabled tool guidance, Skill catalog guidance, execution policy,
retained Skill/memory documents and I editor/evaluator instructions. A candidate can change
multiple H/S components when its runner supports them. IDs, owners and schemas
cannot change within a job. Subagents are not a component category.

`FileComponentAdapter` supports explicitly registered multi-file documents, such
as guardrails, scripts or hooks, with an injected validator. Registration alone
does not make code runnable or publishable. These require a runner and owner
binding implementation. The built-in persistent host publishes registered text
bindings; arbitrary Python/plugin replacement and whole Skill repositories are
unsupported. No empty placeholder implementations are installed.

## Prepare task materials

`TaskMaterial` contains an instruction, resource references, environment identity
and origin. An `ExecutionRecord` contains status, output, trajectory/deliverable
references and available invocation counts. Neither requires a score. Original
binary inputs are preserved. Text evidence is paginated; PNG/JPEG/GIF/WebP can be
read visually, using shared container checks and a 10 MiB image limit. Other
binary formats need an explicit reader. Native task and editor readers do not
decode unsupported binary containers as text.

Every hosted execution also carries `execution-facts.json` as an immutable
diagnostic resource: identities, termination cause, scoped usage, counters,
artifact collection status and granted evidence references. Unknown stays unknown;
collection failure does not prove absence. Native, benchmark and nested editor
executions share this contract without requiring containers. Existing editors read
it through their ordinary evidence workspace; no auxiliary summary is generated.

[Task packages](tasks/README.md) provide optional private scoring and independent
holdout. The first training task supplies diagnosis; all training regression cases, selection and holdout run
only after generation. Answers, checks and holdout inputs are absent from editor
workspaces. Explicit scored feedback is an injected capability and never implied
by benchmark availability. [External receipts](evidence/README.md) retain official
grading outside the behavior-based editing path.

## Start improvement

1. Edit `.fruitfly/experiment.yaml`; choose explicit file material, a task package,
   an editor experiment or an optional Eval source.
2. Run `fruitfly-agent-lab improvement check` to inspect resolved defaults and inputs.
3. Run `fruitfly-agent-lab improvement run` explicitly. Calls may incur model cost.
4. Inspect the run report, evidence and stopping reason. Use `rsi run` for verified
   adoption across generations; benchmark development reward alone is insufficient.

`/improvement [DIRECTION]` retains a light explicit instruction/file/package flow
and result review. It discovers legal targets and uses `simple`; there is no experiment
configuration editor in chat. Advanced component, strategy, feedback, scope and
timing choices belong to experiment files or the public embedding API.

Current-task output selection does not prove improvement or change profile
defaults. Reflection is staged in a separate pending queue. Use Results and history
→ Pending experience to commit or reject it explicitly while idle. A commit is an
attributed S update, not a verified quality claim. Persistent jobs defer library
updates; editor experiments disable experience retention. The library belongs
to S identity and is frozen for each task. Later tasks start from the common
configured harness and the latest committed library, rather than inheriting all
previous task-local edits.

The native runner provides fresh in-memory read/write/edit files, no Bash,
network tools, live Session or production filesystem. Full runtime/SSH/container
execution requires a declared runner. Tool descriptions, schemas and permissions retain their
normal owner contracts.

## Extend search

Register a factory with `GeneratorRegistry.register(id, factory,
implementation_id=..., label=..., required_capabilities=...)`. Discovery reads
metadata without constructing generators or requesting models. Each job receives
a fresh generator instance. Implement `propose(request, services)`; a deterministic
or numerical algorithm can return the same `ProposalResult` without calling an
editor. Model-based algorithms can use the observed `services.complete(system, prompt)`
port without the tool-Agent editor. Every edit needs a supplied execution ID and a registered component.

Inject `WorkflowBindings` into `RunApplicationFactory(improvement_bindings=...)`
to replace any stage, component registry or workflow factory. Generators receive
editing and journaling services; execution, verification and activation remain
separate capabilities. Trusted Python extensions are not an OS sandbox.

## Select execution through public definitions

[Execution definitions](execution/README.md) separate material discovery,
preparation and stage construction. `WorkflowBindings.executions` accepts an
explicit registry. Discovery and preview make no model requests. Run consumes the
public metadata; the terminal renders generic execution choices and parameters.
Unknown IDs/fields and incompatible scopes fail before execution.

[Editor self-improvement](improver/README.md) adds fixed-depth I trials. The outer
job edits I; fresh inner jobs hold I fixed while editing H/S. Private paired trials
measure downstream improvement, regressions and cost. Only I is published, and
only after independent verification. No online component changes occur inside a
task execution.

## Times, usage and failures

Each editor, execution and evaluator invocation has its own time from `RunPlan.timeouts` (defaults: 1200, 3600 and 1200 seconds). Same-invocation nested work shares its clock; composite studies delegate to leaf phases. Counts and reported tokens are observations, with unknown usage explicit. User cancellation propagates; unconfirmed cleanup stops scheduling. Unknown requests are not replayed.

## Results and retention

| Data | Location |
|---|---|
| Plan, frozen task/snapshot, event journal, outcome | `.fruitfly/improvement/jobs/<job-id>/` |
| Submitted-job history, including failure/cancellation | `.fruitfly/improvement/runs/` |
| Pending persistent candidates | `.fruitfly/improvement/candidates/` |
| Pending experience | `.fruitfly/improvement/experience-pending/` |
| Independent-suite use claims | `.fruitfly/improvement/verification-uses.json` |
| Committed experience | `.fruitfly/improvement/experience.json` |
| Immutable text/binary resources and versions | `.fruitfly/artifacts/` |

History verifies journal hashes before reading. Retention follows job, experience, Session, configuration and candidate references. Readers accept the current record/configuration shapes and reject unsupported fields.

## Modules and offline checks

| Module | Responsibility |
|---|---|
| [Execution definitions](execution/README.md) | Material and runner registration without host algorithm branches |
| [Task sets](task_sets/README.md) | Shared candidates, bounded task parallelism, sampling and joint selection |
| [Search strategies](strategies/README.md) | Simple candidate comparison and optional Harness² schedules |
| [Assessment](assessment/README.md) | Read-only completed/online judgments and independent verification |
| [Research](research/README.md) | Task-local ledger, selective retrieval and progress stopping |
| [Termination](termination/README.md) | Composable iteration, resource, score and process conditions |
| [Editor experiments](improver/README.md) | Fixed-depth I comparison and private paired verification |
| [Contracts](../../improvement/contracts/README.md) | Immutable values and public stage protocols |
| [Workflow](workflow/README.md) | Orchestration, accounting and native file execution |
| [Editor](editor/README.md) | Tool workspace editing, output selection and reflection |
| [Materials](materials/README.md) | Explicit workspace input freezing |
| [Evidence](evidence/README.md) | Detached workspace, official receipts and historical reports |
| [Verification](verification/README.md) | Optional private measurements and holdout policy |
| [Experience](experience/README.md) | Attributed lesson serialization and snapshot identity |
| [Task packages](tasks/README.md) | Authoring, validation and independent scoring |

The workflow adapts Propose–Probe–Compose, role-separated editing, output selection
and cross-task experience from [Harness²: Recursive Agent Harnessing for an Open
World](https://arxiv.org/abs/2610.14224). This implementation adds explicit H/S/I
ownership and host verification/adoption. It does not reproduce published scores,
train model weights or claim autonomous unrestricted source rewriting. Editor
instruction experiments implement a bounded, explicitly verified extension.

```bash
.venv/bin/python -m unittest tests.lab.test_improvement_pipeline tests.workflows.test_improvement_pipeline tests.lab.test_improver tests.workflows.test_editor_evolution
```

Offline fake Providers and synthetic rewards establish control flow and isolation,
not model quality, real API compatibility or benchmark gains. The
[offline example](../../../examples/improvement/README.md) uses replaceable ports.

## Separate editing, assessment and evolution

Improvement searches and compares changes. [RSI](../rsi/README.md) adopts eligible
versions and continues with the adopted H/S/I. [Eval](../../../fruitfly_eval/README.md) runs
fixed-version benchmarks and optionally registers execution/official-assessment
ports through its [adapter](../../../fruitfly_eval/improvement/README.md). Eval is not an
Improvement dependency and does not start evolution implicitly.

[Components](components/README.md) own legal changes and publication bindings.
[Assessment](assessment/README.md) owns independent read-only judgments, process
metrics, comparison and verification. [Termination](termination/README.md) owns
composable stopping. The editor diagnoses supplied evidence; task-specific fixes
are not hard-coded into the framework. Existing public stage signatures remain.

File execution can optionally supply online assessment through `assessment_interval`. Completed evaluation uses the shared model evaluator. Judgments do not change live task components or grant activation.

## Use owning public interfaces

[api.py](api.py) exposes reviewed host composition and progress contracts. Generic
values belong to [runtime contracts](../../improvement/contracts/README.md);
concrete editors, assessors, policies and generators belong to their modules.
The API does not provide a parallel contract catalog. Shared
[optimization targets](targets/README.md) retain codecs and state helpers.

Owners supply `OptimizationSpec` explicitly. Text adapters reject a missing
declaration; file adapters require it at construction. Runner admission checks
capabilities, update timing and activation boundary before trials. Declarations
do not grant edits; experiment grants and protected owner fields still apply.
