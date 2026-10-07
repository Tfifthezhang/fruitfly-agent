# Optimization

[Up: Lab](../README.md)

Search and compare improvements to a fixed target. Optimization proposes candidates; Run stores them; Application activates a reviewed candidate in a new session. [RSI](../rsi/README.md) can coordinate independent verification and adoption across generations.

## Start a search

| Step | Action |
|---|---|
| 1 | Prepare a [task pack](TASK_PACKS.md) and run its offline checks. |
| 2 | In **Configure → mechanisms · optimization**, enable **text-optimizer**, select **opro**, save, and start a new session. |
| 3 | Use `/optimize [DIRECTION]`, select the pack, and review target, model, budget, and execution policy. |
| 4 | Confirm **Start search**; monitor `/status` or use `/cancel`. |
| 5 | Review the complete candidate and evidence; save it for later or confirm a new session. |

**Search calls the configured Provider and may incur charges. Python task scoring also executes restricted local functions.** Enabling the mechanism alone does not start a search.

## OPRO research basis

OPRO (Optimization by PROmpting) comes from Yang et al., [Large Language Models as Optimizers](https://arxiv.org/abs/2309.03409v3), Sections 2 and 4. An optimizer model proposes solutions from a task description and previously scored solutions; each new result becomes feedback for subsequent rounds.

| Paper idea | FruitFlyAgent implementation |
|---|---|
| Scored optimization history | Bounded valid candidates, ordered so the best appears last |
| Natural-language objective and examples | Frozen direction and authorized training examples |
| Generate, evaluate, repeat | Baseline evaluation, JSON-array proposals, deduplication, target validation, and train/selection scoring |
| Prompt optimization | `base_prompt` and `skill-catalog.guidance` text targets |
| Published experiments | Not reproduced; no GSM8K/BBH gains or general improvement claims |

This native implementation uses the harness's shared services rather than a research SDK. OPRO is the only built-in search algorithm and is disabled by default.

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

Detailed parameters live in YAML. Model trials use independent, single-turn, no-Session, no-tool Core loops with the target adapter's projection. They do not measure the full interactive harness. Validation is repeatedly used for selection; independent holdout evaluation is manual.

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
| [opro.py](opro.py) | History-driven OPRO search |
| [scoring.py](scoring.py), [python_worker.py](python_worker.py) | Task policies and restricted function scoring |
| [reporting.py](reporting.py) | Search reports, usage, and evidence validation |
| [task_packs.py](task_packs.py), [tasks.py](tasks.py) | Pack catalog, freezing, editing, and read-only case loading |
| [verification.py](verification.py) | Offline material validation, reference checks, scoring, and format conversion |
| [Task packs](TASK_PACKS.md) | Pack format and task-authoring workflow |

## Extend search

Implement `Optimizer.search` with declared schemas/capabilities and register it through [Catalog](../catalog/README.md). Use `HostedTextOptimizer` for shared evaluation and evidence, or implement the narrower `TextOptimizer` contract directly. A deterministic evaluator can run without a model; declare a truthful policy and execution identity. Synchronous evaluators must be fast and bounded.

The optional tool-Agent service uses a private text workspace, no Bash or user files, and at most 8 tool calls by default. It does not have production adoption authority.

| Supported | Not supported |
|---|---|
| Text prompts and catalog guidance | Skill file bodies, multi-file code, arbitrary stateful targets |
| Exact-text and restricted Python scoring | General project-command verification |
| Human review or explicit RSI host | Default background search, automatic holdout execution, automatic quality gate |

No module-specific environment variables; dependencies and model roles are injected. Examples: [Python functions](../../../examples/optimization/python_functions/README.md) and [ticket triage](../../../examples/optimization/ticket_triage/README.md).

```bash
.venv/bin/python -m unittest tests.lab.test_search tests.workflows.test_decoupling tests.workflows.test_optimization -v
```
