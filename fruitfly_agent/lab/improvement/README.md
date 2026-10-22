# Improvement

[Up: Lab](../README.md)

Refine registered Agent components using task execution evidence. The public
[API](api.py) separates candidate generation, execution, composition, selection,
verification, reflection and activation. Run persists jobs; Application owns
execution and adoption. Container benchmark evaluation belongs to the separate Eval consumer.

## Follow a task

```text
Freeze plan, task, H/I/S and experience
  → reference executions
  → propose invariant and domain edits
  → validate component ownership and evidence
  → probe candidates
  → compose and execute
  → select an existing output
  → optionally verify a persistent change
  → reflect and stage attributed experience for explicit review
```

| Stage | Public contract | Default |
|---|---|---|
| Materials | `TaskSource`, `TaskMaterial`, `ArtifactAccess` | Freeze explicitly selected workspace inputs as immutable bytes |
| Components | `ComponentAdapter`, `HarnessSnapshot`, `CandidateBundle` | Object-owned text adapters; complete named file sets |
| Propose | `CandidateGenerator`, `ProposalRequest`, `ProposalResult` | Tool-using editor with invariant/domain missions |
| Probe | `TaskRunner`, `ExecutionRecord` | Detached read/write/edit file workspace |
| Compose | `Composer`, `CompositionRequest` | Editor compares executions and resolves component changes |
| Select | `Selector`, `SelectionDecision` | Read-only comparison of anonymous executed outputs |
| Verify | `VerificationPolicy`, optional `MeasurementSource` | Independent task-package comparison when provided |
| Reflect | `Reflector`, `ExperienceEntry` | Evidence-grounded lesson or no entry |
| Retain | `ExperienceRepository` | Host stages lessons; explicit review precedes an S library update |
| Orchestrate | `WorkflowController` | Bounded parallel or sequential exploration |

Parallel width `k` uses `k` references, `2k` proposals, and `k` compositions when
each proposal returns one candidate. All proposals in one round receive the same
reference evidence and prior history. They cannot inspect their peers. Probes
start after the proposal pool is complete. Sequential mode performs invariant and
domain proposals and one composition per depth. Only a selected incumbent becomes
the next editing baseline; failed or worse compositions do not advance it. Every composition is executed, including an unchanged one.
Generators may return no candidates or request an early stop. The built-in
`parallel` pool is independent but currently awaited sequentially. All successful
executions, including original references and probes, remain selectable.

## Separate feedback, stopping and assurance

| Decision | Rule |
|---|---|
| Propose | Task requirements, declared guidance, trajectories and optional measured feedback supply hypotheses. |
| Stop | `StopPolicy` records round limits, repeated candidates, no candidate or generator stop. Shared allocation exhaustion has its own reason. |
| Select | Consider original and candidate outputs. Measured selection maximizes declared utility and retains the earlier result on ties. Missing measurements retain the incumbent. |
| Retain | Sequential rounds carry the selected configuration rather than the latest composition. |
| Verify | Only an independent policy can grant `verified`; selected outputs remain `selected`. |

Budget stopping is not convergence. Selection without an acceptance policy is a
model judgment, not proof of improvement. `AgentSelector` can return
`NO_CLEAR_CHOICE`; uncertainty or malformed choices retain the first reference.
A completed baseline survives exploratory budget exhaustion. Final selection gets
protected model quota; no complete reference means no invented deliverable.
Timeout/cancellation can still end a job without final selection.

## Choose H, S or I

| Axis | Meaning | Required execution |
|---|---|---|
| H | Execution instructions and mechanisms | Compare task behavior with fixed initial S and I |
| S | Retained knowledge, skills and experience | Declare initial state, updates and reset behavior |
| I | Candidate generation and improvement instructions | Registered [editor comparison](improver/README.md); ordinary task trials reject I edits |

Component kind and H/S/I axis are independent. Existing owners expose the base
prompt, enabled tool guidance, Skill catalog guidance, bounded execution workflow,
retained Skill/memory documents and I editor instructions. A candidate can change
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
binary inputs are preserved. Text evidence is paginated; PNG/JPEG can be read
visually. Other binary formats need an explicit reader.

[Task packages](tasks/README.md) provide optional private scoring and independent
holdout. The first training task supplies diagnosis; all training regression cases, selection and holdout run
only after generation. Answers, checks and holdout inputs are absent from editor
workspaces. Explicit scored feedback is an injected capability and never implied
by benchmark availability. [External receipts](evidence/README.md) retain official
grading outside the behavior-based editing path.

## Start improvement

1. Start a normal session and open `/improvement [DIRECTION]`.
2. Choose an execution strategy, task materials, editable components and a generator.
   Native tasks use explicit instructions/files or task packages; editor experiments
   use a registered experiment manifest.
3. Choose parallel/sequential exploration, allocations, feedback and effect scope.
4. Review the frozen preview and explicitly confirm. Calls may incur model cost.
5. Inspect outputs, assurance, history and logs. Persistent candidates require
   independent verification and remain pending until explicit adoption.

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
editor. Model-based algorithms can use the budgeted `services.complete(system, prompt)`
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

## Budgets and failures

One root allocation covers editor requests and leaf task executions, including
all nested work and independent verification. `BudgetScope` allocates child quotas
without resetting the root or charging a leaf twice. Protected final verification
cannot be consumed by exploration. Preparation rejects insufficient minimum budgets. Reserve before external work. Provider-internal retries are not
separate harness calls. Missing token/cost usage remains unknown. Each operation
has a timeout and shares cancellation. Incomplete, malformed or mismatched
receipts cannot grant verification. Cancellation propagates and does not adopt a
candidate. Model requests with unknown outcomes are not automatically replayed.
Reflection failure is recorded without losing an already selected deliverable.

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

History verifies journal hashes before reading. Retention follows job, experience,
Session, configuration and candidate references. Old candidate/report data remains
readable. Unknown retired mechanism selections are rejected, including disabled
entries; remove them explicitly and configure `component-improvement` as needed.
There is no parallel method selector or legacy search engine.

## Modules and offline checks

| Module | Responsibility |
|---|---|
| [Execution definitions](execution/README.md) | Material and runner registration without host algorithm branches |
| [Editor experiments](improver/README.md) | Fixed-depth I comparison and private paired verification |
| [Contracts](contracts/README.md) | Immutable values and public stage protocols |
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
