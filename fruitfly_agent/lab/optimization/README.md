# Optimization

[Up: Lab](../README.md)

Search and compare improvements to a fixed target. Optimization proposes candidates; Run stores them; Application activates a reviewed candidate in a new session. [RSI](../rsi/README.md) can coordinate independent verification and adoption across generations.

[Automatic text search](automatic/README.md) optionally connects original-task baselines, independent [failure processing](failure_processing/README.md), learning exercises, original-task comparison and one holdout confirmation. A confirmed candidate waits for human adoption. Daily tasks without declared acceptance are not collected by this workflow. [Original task experiments](experiments/README.md) connect official benchmark evidence and isolated full-Application trials to the same workflow.

## Start a search

| Step | Action |
|---|---|
| 1 | Prepare a [task pack](TASK_PACKS.md) and run its offline checks. |
| 2 | In **Configure → mechanisms · optimization**, enable **text-optimizer**, select **opro**, save, and start a new session. |
| 3 | Use `/improvement [DIRECTION]`, select the pack, and review target, model, budget, and execution policy. |
| 4 | Confirm **Start search**; monitor live terminal progress or use `/cancel`. `/status` shows the application state and pending candidate count. |
| 5 | Review the complete candidate and evidence; save it for later or confirm a new session. |

**Search calls the configured Provider and may incur charges. Python task scoring also executes restricted local functions.** Enabling the mechanism alone does not start a search.

## Optimization methods

Each independent method has its own package directly under this module. Shared contracts, evaluation, budgets, evidence, task packs, and hosting remain at the Optimization level. Target adapters belong to the modules that own the objects being changed. A method package may expose an adapter for its own strategy when that capability is implemented.

| Method package | Public entry point | Scope |
|---|---|---|
| [OPRO](opro/README.md) | `opro.OproOptimizer`, `opro.definition()` | History-driven text search using shared services; disabled by default |

OPRO is the only built-in method. Its guide documents the research basis, implemented behavior, and limits. Optimization remains part of Lab and can run independently of RSI and Eval.

## Ownership and contracts

| Concern | Owner / API |
|---|---|
| Target meaning and legal changes | Object's `TextTarget` adapter |
| Frozen problem | `OptimizationProblem`: parent manifest, target snapshot, tasks, objective policy, execution identity |
| Search loop | `Optimizer.search(problem, services) -> SearchResult` |
| Evaluation | `SearchServices.evaluate` returns per-case observations and aggregates. |
| Model/tool capabilities | Injected services with a shared root budget |
| Search evidence | Append-only journal; strategy selects its own bounded history view. |
| Text host | `HostedTextOptimizer` projects a search result to `TextProposal`. |
| Production candidate | Run saves the preferred complete proposal and its evidence. |
| Adoption | Human review or explicitly injected independent RSI policy |
| Learning material | Independently selected [failure processor](failure_processing/README.md); derived exercises retain source, review and scoring identity |
| Automatic confirmation | Optional [workflow](automatic/README.md); fixed original tasks determine whether a learned candidate is publishable |

The shared contract does not require a particular generate/reflect/select sequence. Problems retain fixed task, policy, target, execution, and parent identities. Missing or infrastructure-failed observations have no valid score; task failures may receive zero or partial credit according to policy.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `target` | `base_prompt` | May select enabled `skill-catalog.guidance`. |
| `cases_path` | `.fruitfly/optimization/cases.json` | Optional read-only train/validation source or `pack.json`; job selection can use other registered packs. |
| `rounds` | 2 | Maximum search rounds |
| `batch_size` | 2 | OPRO proposals per round |
| `history_limit` | 5 | History entries shown to the optimizer |
| `max_metric_calls` | 32 | Per-case trials, including baseline and each partition |
| `max_model_calls` | 64 | Harness-level Provider calls across all roles |
| `output_max_tokens` | 1024 | Per-request output limit |
| `call_timeout_seconds` | 30 | Model/evaluation timeout |
| `optimizer_profile` | Empty | Reuse the active Provider, or resolve an explicit model profile. |

Detailed parameters live in YAML. Default model trials use independent, single-turn, no-Session, no-tool Core loops with the target adapter's projection. They do not measure the full interactive harness. Validation is repeatedly used for selection. Holdout is manual in ordinary search and automatically checked once by the optional automatic workflow. Injected [trial executors](automatic/README.md#inspect-evidence-and-extend-execution) can run fresh task-owned tool harnesses.

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
| Exhausted budget | Return only already complete candidates; normal conversation remains available. |
| Cancellation | No candidate returned. |
| Interrupted paid work | Record intent and response separately; do not replay unknown calls automatically. |

With 8 training and 4 selection cases, one full evaluation consumes 12 trials. A budget of 32 permits baseline, one complete candidate, and 8 additional training trials.

## Results and retention

| Data / action | Behavior |
|---|---|
| Candidate inbox | `.fruitfly/optimization/candidates/`; one preferred complete result per configuration/profile/target/task pack |
| Text artifact | `.fruitfly/artifacts/`; immutable contents used by runtime and recovery |
| Search journal | `.fruitfly/optimization/searches/<search_id>.jsonl` |
| Readable result | `.fruitfly/optimization/task-results/<pack-id>/<config-profile-scope>/<target>/latest.txt` and `latest.json` |
| Save for later | Save the next-session default without replacing the active session. |
| Use for a new session | Confirm, validate parent/artifact/configuration, then activate a new empty session. |
| Retention | Protect configuration, Session, candidate-parent, and RSI references; stop cleanup on suspicious or damaged references. |

Latest does not mean better. Failed, cancelled, or empty searches do not replace prior complete results. Cleanup does not sweep arbitrary artifacts or failed searches with no candidate. Export research evidence explicitly. Editing `latest.txt` does not change the runtime. Activation does not roll back external effects, reload source, or create a cross-process transaction.

## Files

| File | Responsibility |
|---|---|
| [search.py](search.py) | Problems, strategies, observations, policies, and candidates |
| [services.py](services.py) | Evaluation, budgets, model/tool services, and journal |
| [host.py](host.py), [text_optimizer.py](text_optimizer.py) | Shared text host and Run-facing preview/search/cancel contract |
| [registration.py](registration.py) | Shared target/budget parameters and text optimizer assembly |
| [OPRO](opro/README.md) | Independent history-driven text optimization method |
| [scoring.py](scoring.py), [python_worker.py](python_worker.py) | Task policies and restricted function scoring |
| [reporting.py](reporting.py) | Search reports, usage, and evidence validation |
| [task_packs.py](task_packs.py), [tasks.py](tasks.py) | Pack catalog, freezing, editing, and read-only case loading |
| [verification.py](verification.py) | Offline material validation, reference checks, scoring, and format conversion |
| [Task packs](TASK_PACKS.md) | Pack format and task-authoring workflow |
| [Failure processing](failure_processing/README.md) | Independent replay, model-generated exercises and material review |
| [Automatic search](automatic/README.md) | Original-task gates, early stopping and independent confirmation |
| [trials.py](trials.py), [execution.py](execution.py) | Batch receipts and isolated task-harness executor contracts |

## Extend search

Create one package per independent method directly under `optimization/`, with a public entry point in `__init__.py` and an English README. Keep method-specific prompts and state beside its implementation when needed. The README must describe the research source, supported targets, injected capabilities, parameters, state/reset/recovery, budgets, failure/cancellation, limits, and offline checks. Do not create placeholder files for unsupported capabilities.

Own the method's Catalog definition and installer in that package, as [OPRO](opro/README.md) does. For a native text method, reuse `text_target_parameters`, `text_budget_parameters`, and `install_text_optimizer` from [registration.py](registration.py). Declare method-specific parameters and model roles explicitly; assembly resolves only those roles. Definition construction and installation must not start research or make model requests.

Implement `Optimizer.search` with declared schemas/capabilities and register it through [Catalog](../catalog/README.md). Use `HostedTextOptimizer` for shared evaluation and evidence, or implement the narrower `TextOptimizer` contract directly. A deterministic evaluator can run without a model; declare a truthful policy and execution identity. Synchronous evaluators must be fast and bounded.

Reuse shared services for trials, budgets, journals, and results. Run and frontends consume the common host contract; adding a method must not add algorithm-specific branches there. Registration is explicit through Catalog definitions, not automatic package discovery. Algorithm tests belong in the project's `tests/` tree.

The optional tool-Agent service uses a private text workspace, no Bash or user files, and at most 8 tool calls by default. It does not have production adoption authority.

| Supported | Not supported |
|---|---|
| Text prompts and catalog guidance | Skill file bodies, multi-file code, arbitrary stateful targets |
| Exact-text and restricted Python scoring | General project-command verification |
| Human review, optional automatic confirmation, or explicit RSI host | Default background search, autonomous adoption, weak-feedback daily-task learning |

No module-specific environment variables; dependencies and model roles are injected. Examples: [Python functions](../../../examples/optimization/python_functions/README.md), [ticket triage](../../../examples/optimization/ticket_triage/README.md), and [offline automatic search](../../../examples/optimization/automatic_text/README.md).

```bash
.venv/bin/python -m unittest tests.lab.test_search tests.workflows.test_decoupling tests.workflows.test_optimization -v
```
