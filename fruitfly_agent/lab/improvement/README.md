# Improvement

[Up: Lab](../README.md)

Refine registered Agent components using task execution evidence. The public
[API](api.py) separates candidate generation, execution, composition, selection,
verification, reflection and activation. Run persists jobs; Application owns
execution and adoption. Eval remains an optional external task consumer.

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
  → reflect and commit attributed experience at the task boundary
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
| Retain | `ExperienceRepository` | Host commits after a completed task; no activation authority |
| Orchestrate | `WorkflowController` | Bounded parallel or sequential exploration |

Parallel width `k` uses `k` references, `2k` proposals, and `k` compositions when
each proposal returns one candidate. All proposals in one round receive the same
reference evidence and prior history. They cannot inspect their peers. Probes
start after the proposal pool is complete. Sequential mode performs invariant and
domain proposals and one composition per depth, carrying prior edits and execution
evidence forward. Every composition is executed, including an unchanged one.
Generators may return no candidates or request an early stop.

## Choose H, S or I

| Axis | Meaning | Required execution |
|---|---|---|
| H | Execution instructions and mechanisms | Compare task behavior with fixed initial S and I |
| S | Retained knowledge, skills and experience | Declare initial state, updates and reset behavior |
| I | Candidate generation and improvement instructions | Explicit improver-comparison runner; ordinary task trials reject I edits |

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
2. Choose a current instruction and input files, a saved task package, or an
   available benchmark task stream. Select editable components and a generator.
3. Choose parallel/sequential exploration, allocations, feedback and effect scope.
4. Review the frozen preview and explicitly confirm. Calls may incur model cost;
   external streams also download task material and execute containers.
5. Inspect outputs, assurance, history and logs. Persistent candidates require
   independent verification and remain pending until explicit adoption.

Current-task output selection does not prove improvement or change profile
defaults. Pending reflection is committed to a separate experience library after
that task completes. Persistent jobs defer library updates. The library belongs
to S identity and is frozen for each task. Later tasks start from the common
configured harness and the latest committed library, rather than inheriting all
previous task-local edits.

The native runner provides fresh in-memory read/write/edit files, no Bash,
network tools, live Session or production filesystem. Full runtime/SSH/container
execution requires a declared runner. External benchmark streams reuse normal
Application trials and produce task-local outputs; they do not claim independent
persistent verification. Tool descriptions, schemas and permissions retain their
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

## Budgets and failures

One root allocation covers editor requests and task executions, including
verification. Reserve before external work. Provider-internal retries are not
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
train model weights or autonomously rewrite the improver.

```bash
.venv/bin/python -m unittest tests.lab.test_improvement_pipeline tests.workflows.test_improvement_pipeline tests.workflows.test_benchmark_improvement
```

Offline fake Providers and synthetic rewards establish control flow and isolation,
not model quality, real API compatibility or benchmark gains. The
[offline example](../../../examples/improvement/README.md) uses replaceable ports.
