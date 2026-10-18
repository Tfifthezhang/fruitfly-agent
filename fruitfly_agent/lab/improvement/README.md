# Improvement

[Up: Lab](../README.md)

Search and compare improvements to a fixed target. Improvement proposes candidates; Run stores them; Application activates a reviewed candidate in a new session. [RSI](../rsi/README.md) can coordinate independent verification and adoption across generations.

## Choose H, S or I

| Role | Object | Comparison |
|---|---|---|
| H: Harness | Execution instructions and mechanisms | Fix I and initial S; compare task outcomes |
| S: State | Retained skills, memory and knowledge | Fix H and I; declare initial state and update/reset rules |
| I: Improver | Candidate generation, processing and search mechanisms | Use the same initial system and budget; compare the resulting improvements |

Classification follows use, not file format. Base prompts and Skill catalog
guidance are H; retained Skill bodies are S. The final task/scoring policy,
model allocation and budgets are external comparison conditions.

[Methods](methods/README.md) contain OPRO, Tree search, DreamRSI, Workflow search, Skill document optimization and Exploratory memory learning. S supports registered retained Skill and memory documents; DreamRSI supports the registered I exploration-policy artifact. Shared [contracts](contracts/__init__.py), [versions](contracts/versions.py),
[candidates](contracts/candidates.py) and [workflow](runtime/workflow.py) support explicit embedding
capabilities for all three roles. One job modifies one role and one target.
`ImprovementWorkflow` rejects absent comparison capabilities, stale parents,
scope changes and mismatched evidence; prepared trials close on rejection or
cancellation. An optional host adopter must activate the exact verified version.
Concrete targets remain owned by their original modules.

The standard host supports H instructions and bounded workflows, registered S documents, and registered I policy artifacts. The generic role workflow is an embedding
entry, not an arbitrary state or source-replacement implementation. Daily
[learning material production](../learning/README.md) is separately configured;
in-job failure processing continues to operate on scored training failures.

[Automatic text search](automatic/README.md) optionally connects original-task baselines, independent [failure processing](failure_processing/README.md), learning exercises, original-task comparison and one holdout confirmation. A confirmed candidate waits for human adoption. Daily tasks without declared acceptance are not collected by this workflow. [Original task experiments](experiments/README.md) connect official benchmark evidence and isolated full-Application trials to the same workflow.

## Start a search

| Step | Action |
|---|---|
| 1 | Prepare a [task pack](tasks/README.md) and run its offline checks. |
| 2 | Start a normal session with a configured model. No improvement switch is required. |
| 3 | Use `/improvement [DIRECTION]`; expand Target, select an object and then its algorithm inline. Set Task and Budget; inspect Evaluation. Inspect the algorithm description and paths; edit optional Search guidance under Target. |
| 4 | Choose **Start improvement** and confirm; inspect the running view or return to chat and use `/status` or `/cancel`. |
| 5 | Inspect the result and stop reason, including empty outcomes. Review any candidate before setting the future default or activating a new session. |

**Search calls the configured Provider and may incur charges. Python task scoring also executes restricted local functions.** Only explicit confirmation starts a search; registering methods does not run them.

## Improvement methods

Each independent method has its own package under `methods/`. Shared contracts, evaluation, budgets, evidence, task packs, and hosting remain at the Improvement level. Target adapters belong to the modules that own the objects being changed. A method package may expose an adapter for its own strategy when that capability is implemented.

| Method package | Public entry point | Scope |
|---|---|---|
| [OPRO](methods/opro/README.md) | `opro.OproImprover`, `opro.definition()` | History-driven H text search; available on demand |
| [Tree search](methods/tree_search/README.md) | `TreeSearchImprover`, `definition()` | H discovery histories and an I exploration-policy target |
| [DreamRSI](methods/dream_rsi/README.md) | `DreamRsiImprover`, `definition()` | Replay-based I policy refinement with real confirmation |
| [Workflow search](methods/workflow_search/README.md) | `WorkflowSearchImprover`, `definition()` | H stage workflows with reflection, repair and design archives |
| [Skill document optimization](methods/skill_edit/README.md) | `SkillEditImprover`, `definition()` | S Skill body updates under a bounded edit allowance |
| [Exploratory memory learning](methods/memory_exploration/README.md) | `MemoryExplorationImprover`, `definition()` | S knowledge from authorized broad/focused practice |

Method guides document their research basis, implemented behavior, and limits. Improvement remains part of Lab and can run independently of RSI and Eval.

## Select methods without changing defaults

Catalog contributions retain the existing `layer × family` classification. H/S/I identifies the object changed by a job. Internal analysis, practice selection and patch operations do not create additional classification axes. [Method declarations](methods/README.md) describe support; [runtime selection](runtime/README.md) checks executable bindings.

`/improvement` selects role, target, method and task source. Select a target first, then explicitly select an algorithm below it, including when only one is available. Remembered defaults are suggestions; compatible prior selections can remain when changing targets. Methods incompatible with the target role or schema are omitted. Compatible methods explain missing runtime capabilities; an empty catalog blocks startup. Per-job choices do not change YAML or the parent I version. Target shows concise algorithm descriptions and implementation/guide paths. The panel expands typed Budget fields and declared material fields under Task; internal tuning uses the displayed configuration location. Input retains the panel and focused field while showing descriptions, current values, types and bounds. The terminal exposes no internal tuning fields or JSON override editor. YAML defaults and programmatic parameter overrides remain available; unknown fields and invalid values are rejected before search. Confirmed method/parameter choices are remembered per configuration/profile/target in workspace preferences. Saved preferences are editable defaults, not evidence or activation. Confirmation binds implementation, normalized parameters, tasks and parent H/S/I. Programmatic previews accept `method_id`, `target_id` and optional `parameters`; changing auxiliary model profiles requires configuration and a new session.

Scoring and acceptance differ from natural-language search guidance. The task policy and method determine comparisons; empty guidance does not remove those rules. Methods declare `direction_help` to expose optional guidance input. OPRO and Tree search use it for candidate proposals. DreamRSI uses its replay objective and confirmation rules; its fixed inner-search direction is a separate method parameter and must match the discovery histories. The shared search contract permits empty guidance. Preview receipts bind it exactly, including an empty string.

The public [api.py](api.py) facade supplies host views, reports and optional experiment types. Run consumes it and the task-material API; it does not import concrete method implementations.

## Inspect requirements and feedback

Built-in methods supply `MethodUsage` fields in their previews: trigger, required materials, feedback, candidate generator, acceptance and activation. Task execution scores, replay objectives and independent confirmation are distinct evidence. Configuration does not trigger optimization. Use `/improvement` explicitly; timer/event scheduling is not installed.

DreamRSI needs the registered tree-search policy target, matching completed histories and a schema-2 task pack with holdout. Follow [DreamRSI preparation](methods/dream_rsi/README.md#prepare-inputs) before starting I improvement. Missing or changed materials fail before model requests.

Enable the object mechanism before selecting Workflow search (`execution-workflow`), Skill document optimization (`skill-document`) or Exploratory memory learning (`learned-memory`). Skill and memory are Context augmentation mechanisms; workflow is an execution mechanism. These methods require disjoint train/selection/holdout. The host confirms only the selection winner once, allows an independent tie, and rejects aggregate or per-case regression. Confirmation evidence is not supplied to generation. [Offline example](../../../examples/improvement/native_methods/README.md).

## Ownership and contracts

| Concern | Owner / API |
|---|---|
| Target meaning and legal changes | Object's `TextTarget` adapter |
| Frozen problem | `ImprovementProblem`: parent manifest, role-bearing target snapshot, tasks, objective policy, execution identity; the standard host also freezes H/S/I |
| Search loop | `Improver.search(problem, services) -> SearchResult` |
| Evaluation | `SearchServices.evaluate` returns per-case observations and aggregates. |
| Model/tool capabilities | Injected services with a shared root budget |
| Search evidence | Append-only journal; strategy selects its own bounded history view. |
| Text host | `HostedTextImprover` projects a search result to `TextProposal`. |
| Production candidate | Run saves the preferred complete proposal and its evidence. |
| Adoption | Human review or explicitly injected independent RSI policy |
| Learning material | Independently selected [failure processor](failure_processing/README.md); derived exercises retain source, review and scoring identity |
| Automatic confirmation | Optional [workflow](automatic/README.md); fixed original tasks determine whether a learned candidate is publishable |

The shared contract does not require a particular generate/reflect/select sequence. Problems retain fixed task, policy, target, execution, and parent identities. Missing or infrastructure-failed observations have no valid score; task failures may receive zero or partial credit according to policy.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `target` | `base_prompt` | May select enabled `skill-catalog.guidance`. |
| `cases_path` | `.fruitfly/improvement/cases.json` | Optional read-only train/validation source or `pack.json`; job selection can use other registered packs. |
| `rounds` | 2 | Maximum search rounds |
| `batch_size` | 2 | OPRO proposals per round |
| `history_limit` | 5 | History entries shown to the improver |
| `max_metric_calls` | 32 | Per-case trials, including baseline and each partition |
| `max_model_calls` | 64 | Harness-level Provider calls across all roles |
| `output_max_tokens` | 1024 | Per-request output limit |
| `call_timeout_seconds` | 30 | Model/evaluation timeout |
| `improver_profile` | Empty | Reuse the active Provider, or resolve an explicit model profile. |

Parameters can be overridden on the experiment panel or supplied programmatically. Existing YAML method entries remain optional defaults; `enabled: false` does not hide a registered method. Legacy enabled hosts remain supported. Improvement has no configuration-menu category. Default model trials use independent, no-Session, no-tool Core loops with the target adapter's projection. Registered retained documents and bounded execution workflows remain fixed when another target changes. A workflow runs its declared stages; other native trials are single-turn. These trials do not measure the full interactive harness or retrieve arbitrary file context. Validation is repeatedly used for selection. The three workflow/document methods require host-owned holdout confirmation; OPRO/Tree search use manual independent testing or the optional automatic workflow. Injected [trial executors](automatic/README.md#inspect-evidence-and-extend-execution) can run fresh task-owned tool harnesses.

## Budgets, progress, and failure

| Concern | Behavior |
|---|---|
| Call accounting | Reserve before harness Provider calls and each case; adapter-internal retries are not separate budget calls. |
| Output limit | Built-in Providers use the smaller of the trial limit and constructor limit. |
| Token reporting | Actual available receipts; missing usage stays unknown. Cache counters are separate. |
| Cost | Call limits are not cumulative token or monetary limits. |
| Progress | Phase, current batch completed/total, call/trial usage, and infrastructure failures |
| Percentage | Batch progress only; no overall completion percentage or time estimate. |
| Observer failure | Does not stop the authorized search. |
| Exhausted budget | Return only already complete candidates; mandatory confirmation cannot be skipped; normal conversation remains available. |
| Cancellation | No candidate returned. |
| Interrupted paid work | Record intent and response separately; do not replay unknown calls automatically. |

With 8 training and 4 selection cases, one full evaluation consumes 12 trials. A budget of 32 permits baseline, one complete candidate, and 8 additional training trials.

## Results and retention

| Data / action | Behavior |
|---|---|
| Experiment history | `.fruitfly/improvement/runs/`; submitted jobs, including empty/failed/cancelled outcomes, scoped to configuration/profile |
| Candidate inbox | `.fruitfly/improvement/candidates/`; one preferred complete result per configuration/profile/target/task pack |
| Text artifact | `.fruitfly/artifacts/`; immutable contents used by runtime and recovery |
| Search journal | `.fruitfly/improvement/searches/<search_id>.jsonl` |
| Readable result | `.fruitfly/improvement/task-results/<pack-id>/<config-profile-scope>/<target>/latest.txt` and `latest.json` |
| Set as next-session default | Confirm a saved configuration change without replacing the active session. |
| Set default and start a new session | Confirm, validate parent/artifact/configuration, then activate a new empty session. |
| Retention | Protect configuration, Session, candidate-parent, and RSI references; stop cleanup on suspicious or damaged references. |

Experiment summaries retain stop reasons, available measurements and journal references independently of candidate publication. Referenced candidates and evidence remain protected; history is not automatically pruned. Interrupted records are not replayed.

Latest does not mean better. Failed, cancelled, or empty searches do not replace prior complete results. Cleanup does not sweep arbitrary artifacts or failed searches with no candidate. Export research evidence explicitly. Editing `latest.txt` does not change the runtime. Activation does not roll back external effects, reload source, or create a cross-process transaction.

## Files

| File | Responsibility |
|---|---|
| [Contracts](contracts/README.md) | Parent versions, declared changes, target scope and comparison evidence |
| [search.py](contracts/search.py) | Problems, strategies, observations, policies, and candidates |
| [Runtime](runtime/README.md), [services.py](runtime/services.py) | Evaluation, budgets, model/tool services, and journal |
| [host.py](runtime/host.py), [api.py](api.py) | Shared text host and Run-facing preview/search/cancel contract |
| [registration.py](registration.py) | Shared target/budget parameters and text improver assembly |
| [OPRO](methods/opro/README.md) | Independent history-driven text improvement method |
| [scoring.py](tasks/scoring.py), [python_worker.py](tasks/python_worker.py) | Task policies and restricted function scoring |
| [reporting.py](runtime/reporting.py) | Search reports, usage, and evidence validation |
| [Task materials](tasks/README.md), [cases.py](tasks/cases.py) | Pack catalog, freezing, editing, and read-only case loading |
| [verification.py](tasks/verification.py) | Offline material validation, reference checks, scoring, and format conversion |
| [Task packs](tasks/README.md) | Pack format and task-authoring workflow |
| [Failure processing](failure_processing/README.md) | Independent replay, model-generated exercises and material review |
| [Automatic search](automatic/README.md) | Original-task gates, early stopping and independent confirmation |
| [Trials](trials/README.md), [execution.py](trials/execution.py) | Batch receipts and isolated task-harness executor contracts |

## Extend search

Create one package per independent method under `improvement/methods/`, with a public entry point in `__init__.py` and an English README. Keep method-specific prompts and state beside its implementation when needed. The README must describe the research source, supported targets, injected capabilities, parameters, state/reset/recovery, budgets, failure/cancellation, limits, and offline checks. Do not create placeholder files for unsupported capabilities.

Own the method's Catalog definition, per-job binding declaration and installer in that package, as [OPRO](methods/opro/README.md) does. For a native text method, reuse `text_target_parameters`, `text_budget_parameters`, and `install_text_improver` from [registration.py](registration.py). Declare method-specific parameters and model roles explicitly; assembly resolves only those roles. Definition construction and installation must not start research or make model requests.

Implement `Improver.search` with declared schemas/capabilities and register it through [Catalog](../catalog/README.md). Use `HostedTextImprover` for shared evaluation and evidence, or implement the narrower `TextImprover` contract directly. A deterministic evaluator can run without a model; declare a truthful policy and execution identity. Synchronous evaluators must be fast and bounded.

Reuse shared services for trials, budgets, journals, and results. Run and frontends consume the common host contract; adding a method must not add algorithm-specific branches there. Registration is explicit through Catalog definitions, not automatic package discovery. Algorithm tests belong in the project's `tests/` tree.

The optional tool-Agent service uses a private text workspace, no Bash or user files, and at most 8 tool calls by default. It does not have production adoption authority.

| Supported | Not supported |
|---|---|
| H prompts/guidance, bounded workflows, S retained Skill/memory documents and I declarative exploration policies | Multi-file code, whole Skill repositories, arbitrary stateful targets |
| Exact-text and restricted Python scoring | General project-command verification |
| Human review, optional automatic confirmation, or explicit RSI host | Default background search, autonomous adoption, weak-feedback daily-task learning |

No module-specific environment variables; dependencies and model roles are injected. Examples: [Python functions](../../../examples/improvement/python_functions/README.md), [ticket triage](../../../examples/improvement/ticket_triage/README.md), and [offline automatic search](../../../examples/improvement/automatic_text/README.md).

```bash
.venv/bin/python -m unittest tests.lab.test_search tests.workflows.test_decoupling tests.workflows.test_improvement -v
```
