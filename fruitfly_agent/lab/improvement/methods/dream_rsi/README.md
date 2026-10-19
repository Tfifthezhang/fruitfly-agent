# DreamRSI

[Up: Improvement Methods](../README.md)

Improve I's exploration policy using frozen discovery histories, then confirm the selected policy through fresh searches and independent task outcomes. H, initial S, the candidate generator, task scorer and comparison conditions remain fixed.

## Research basis and implemented scope

Based on Zheng et al., [Dream-RSI: Recursive Self-Improvement through Evolving Worlds](https://arxiv.org/abs/2609.14858), Section 3, version 2. This is an independent implementation from the paper, not a wrapper around released upstream code.

| Paper mechanism | Implementation |
|---|---|
| Real discovery histories as worlds | Immutable parent-linked scored text attempts from [Tree search](../tree_search/README.md) |
| Shared online/replay decision interface | Same bounded policy selects root or currently observed leaves |
| Prefix-only replay | Reveal recorded successors; root branches open in creation order; never generate missing outcomes |
| Quality/cost replay reward | Five budget preferences, normalized nondominated frontier hypervolume, and sequential-rounds-per-call penalty |
| Policy improvement | Model proposes bounded declarative policy JSON; no arbitrary Python policy-code generation |
| Growing world pool | Real confirmation searches and later H tree searches append histories; the current job's input pool stays frozen |
| Deployment | Human-reviewed I artifact activation; subsequent tree searches load the policy |
| Additional product confirmation | One selected policy is tested with paired real searches and a separate holdout task set |

The restricted four-field policy family, text-only discovery and mandatory independent confirmation are explicit adaptations. No published model, kernel, algorithm-engineering or benchmark gains are reproduced. Replay only measures behavior on recorded paths; it does not predict unobserved outcomes.

## Prepare inputs

1. Start a normal session with a configured model. Tree search and its I policy target are registered without an enable switch.
2. Install a schema-2 [task pack](../../tasks/README.md) with train, selection and nonempty holdout. Exact labels or restricted Python function tests provide automatic scores; no human numerical score is required.
3. Run H tree search with the fixed discovery direction, for example `/improvement Improve task performance.`. Keep the initial H unchanged; saving an H candidate is optional and should wait if reusing the original histories.
4. Keep the same model, task/scoring execution identity, initial text and training/selection inputs. Histories must contain at least one positive scored outcome to normalize the paper objective.
5. Open `/improvement`; expand **Target**, select Exploration policy under I and DreamRSI below it, then set **Task** to the saved pack. Review the panel, choose **Start improvement** and confirm.

The default history directory is `.fruitfly/improvement/discovery`. Use a separate directory per fixed context; `history_path` can also select one completed JSON history. Malformed or mismatched histories fail before model work. Zero-quality worlds cannot support the paper's normalization and are explicitly excluded and counted in preview/journal; an entirely zero-quality pool is rejected.

The task pack remains compatible with the underlying H target such as `base_prompt`. DreamRSI projects that task source to the I policy target; do not relabel the task answers as policy scores. Task answers score task execution, while the replay objective scores exploration.

## Configure method entries

Optional method defaults can be stored as mechanism entries inside the selected harness profile. They are not required for discovery or execution. Use **Budget** limits and **Task** material fields, including the fixed discovery direction, for per-job settings. **Target** shows the description; Details reveals implementation/guide paths and the configuration location; tune internal policy parameters in YAML at the configuration location in Details or through programmatic previews. Fields show current values, descriptions and type/bounds, and display text while typing. Keep other mechanisms and model settings as required by your workspace. Legacy enabled hosts remain supported.

Evaluation exposes the comparison rules; Target has no generic guidance input for this method. Replay scoring and real-search confirmation determine selection and acceptance. The separate `discovery_direction` field configures the inner H search and must match the recorded discovery histories; it does not redefine the replay objective.

```yaml
- id: tree-search
  enabled: false
  parameters:
    target: base_prompt
    cases_path: .fruitfly/improvement/task-packs/ticket-triage/pack.json
    rounds: 4
    workers: 2
    discovery_calls: 8
    history_path: .fruitfly/improvement/discovery
- id: dream-rsi
  enabled: false
  parameters:
    history_path: .fruitfly/improvement/discovery
    discovery_direction: Improve task performance.
    policy_revisions: 3
    confirmation_repeats: 1
```

The installed [ticket example](../../../../../examples/improvement/ticket_triage/README.md) illustrates format only. Real search uses the configured Provider and may incur charges. Ensure the initial H text is suitable for your tasks. Collection and optimization both require explicit jobs; configuration starts neither.

## Inspect the usage contract

| Question | Behavior |
|---|---|
| Trigger | Manual `/improvement`; no timer, event scheduler or background search |
| Target | I / `tree-search.exploration-policy` |
| Materials | 1–32 bounded completed histories and a task pack with independent holdout |
| Feedback | Actual recorded task scores; replay returns existing outcomes without model or evaluator requests |
| Candidate generation | Configured model proposes width, root frequency, ranking and stop fraction |
| Selection | Average paper replay reward across eligible frozen worlds |
| Final confirmation | Same initial H and fixed search ceilings for current/candidate policies; each search chooses its best selection candidate, then evaluates it on holdout |
| Acceptance | Strict holdout mean gain of `min_online_gain`, or nondecreasing holdout mean with fewer discovery calls |
| Activation | Review, save or activate in a new session; the I identity changes, H/S remain fixed |

The confirmation ceilings are equal; actual calls may differ. A quality gain can qualify within that ceiling even if it uses more calls. Equal quality qualifies only with fewer calls. Default one-repeat confirmation is not statistical proof. Repeated use of the same holdout across jobs weakens independence; maintain research splits externally. Only one policy is confirmed per job; failed confirmation does not retry another policy on that holdout.

## Budgets, evidence and failure

| Parameter | Default |
|---|---|
| `policy_revisions` | 3 |
| `replay_rounds` | 64 per world/preference |
| `replay_timeout_seconds` | 30 per policy sweep |
| `parallel_penalty` | .1 |
| `min_replay_gain` | .001 |
| `min_online_gain` | .01 |
| `confirmation_repeats` | 1 paired comparison |
| `rounds`, `workers`, `discovery_calls` | 4, 2, 8 per real search |
| `max_model_calls`, `max_metric_calls` | 64, 64 for the entire job |

Generation, task trials and confirmation share one root budget, cancellation signal and usage ledger. Historical replay's represented calls are separate from actual model usage. Replay runs in a worker thread with bounded rounds/deadline and cooperative cancellation checks. A timeout signals cancellation; no candidate is published. Incomplete observations have no valid score. Cancellation or exhausted confirmation cannot produce an accepted candidate.

Preview binds source file hashes, method parameters, task identity and parent H/S/I. New records can be appended, but changing a selected input record invalidates the receipt. Journals record replay results, excluded histories, actual discoveries and confirmation. History files may contain task material and model output; they are local research artifacts, not packaged source.

[Run](../../../../run/improvement/README.md) owns storage and activation. The method cannot adopt itself. Existing [RSI drivers](../../../rsi/README.md) remain separate; this integration provides an explicit manual multi-generation loop, not a default autonomous coordinator.

## Files and offline checks

| File | Responsibility |
|---|---|
| [registration.py](registration.py) | Catalog declaration, parameters and H-task/I-target projection |
| [improver.py](improver.py) | Frozen pool, policy refinement, real-search and holdout confirmation |
| [replay.py](replay.py) | Prefix transitions, objective and deterministic replay evidence |
| [__init__.py](__init__.py) | Public method and replay entries |

```bash
.venv/bin/python -m unittest tests.lab.test_dream_rsi tests.workflows.test_dream_rsi
.venv/bin/python -m examples.improvement.dream_rsi
```

The [offline example](../../../../../examples/improvement/dream_rsi/README.md) makes no model requests. Tests use synthetic histories and fake Providers; passing them establishes mechanics, not real quality gains. There are no method-specific environment variables.
