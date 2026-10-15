# Automatic Text Search

[Up: Optimization](../README.md)

Run a bounded task-feedback experiment over a fixed text target. Publish a candidate only after original-task improvement and independent confirmation. The existing candidate menu keeps adoption under human control. This workflow is not autonomous background learning or RSI.

## Configure a job

Enable OPRO, choose one [Failure processing](../failure_processing/README.md) method, and enable `automatic-text-search`. Start a new session. All mechanisms are disabled by default. Prepare a schema-2 task pack with train, selection (`validation`), and nonempty holdout; legacy train/validation files cannot provide independent confirmation.

The following is a mechanism-list fragment for an existing profile, not a complete configuration:

```yaml
mechanisms:
  - id: opro
    enabled: true
    parameters:
      rounds: 3
      batch_size: 2
      max_metric_calls: 128
      max_model_calls: 160
      output_max_tokens: 4096
  - id: failure-distillation
    enabled: true
    parameters:
      materializer_profile: ""
      material_reviewer_profile: ""
  - id: automatic-text-search
    enabled: true
    parameters:
      min_improvement: 0.05
      max_case_regression: 0.0
      failure_threshold: 1.0
      material_limit: 4
      confirmation_repeats: 1
      timeout_seconds: 600
```

Select `failure-replay` instead to reuse failed tasks without material-generation calls. Use `/improvement` to select the pack, inspect the workflow, models, confirmation count and budgets, and explicitly start one paid job. Configuration and assembly do not start research.

## Follow the experiment

| Step | Behavior |
|---|---|
| Freeze | Verify task package identity, scorer, target and current parent; privately freeze confirmation tasks |
| Baseline | Run original training and selection tasks; missing or infrastructure-failed scores stop the job |
| Prepare | Select scored training failures and invoke the chosen processor; validate provenance, bounds and partition separation |
| Learn | Evaluate frozen learning exercises and use their observations to generate text candidates |
| Select | Evaluate candidates on unchanged original selection tasks; use these scores for candidate history and ranking |
| Check regressions | For a candidate meeting the gain threshold, rerun all original training tasks and reject disallowed per-case regressions |
| Confirm | Stop generation, run original holdout inputs with baseline and candidate once, with the configured repeats |
| Review | Publish one confirmed candidate; retain the active runtime until the user saves or adopts it |

OPRO supports the optional `candidate_evaluated` callback to stop at the first eligible candidate. Other injected strategies may finish their bounded search first. Strategies receive a learning/selection view, not the confirmation capability. No holdout contents or expected answers are included in generation or material review. Trusted Python extensions are not sandboxed by this boundary.

Learning tasks can differ from original tasks. Their scores are learning feedback, not the headline improvement metric. The journal records learning policy/execution identities separately; the candidate report's training and selection fields describe original tasks. Derived material is frozen for one search; changing it between rounds is not implemented.

## Set stopping and resource rules

| Parameter | Default | Rule |
|---|---|---|
| `min_improvement` | 0.05 | Minimum objective utility gain on both original selection and independent confirmation |
| `max_case_regression` | 0 | Maximum utility decline per original training case and per confirmation case/repeat |
| `failure_threshold` | 1 | Scores below this value are training failures for maximization; minimization reverses the comparison |
| `material_limit` | 4 | Maximum learning tasks, 1–12 |
| `confirmation_repeats` | 1 | Fresh baseline and candidate trials, 1–5 repeats |
| `timeout_seconds` | 600 | Whole workflow deadline, in addition to per-operation limits |

Choose score thresholds for the declared metric. A threshold does not establish statistical significance. Model calls, source trials, generated exercises and confirmation share one root budget. Repeated seeds and model versions do not guarantee identical responses. Provider-internal retries remain opaque, and call limits are not monetary limits.

With `T` train, `V` selection, `L` learning tasks, `H` holdout and `R` confirmation repeats, one first eligible candidate needs `2T + 2V + 2L + 2HR` task trials. Additional candidates consume learning/selection trials and sometimes original regression trials. The preview shows the minimum for one learning task; it is not a prediction of total work. Increase OPRO budgets before starting larger packs.

| Stop | Outcome |
|---|---|
| `confirmed_improvement` | One candidate waiting for human review |
| `confirmation_failed` | No candidate; no further search on the same holdout in this job |
| `no_improvement` / `no_scored_failures` | No candidate |
| `baseline_unavailable` | No candidate; inspect task/infrastructure failures |
| `budget_exhausted` / `workflow_timeout` | No unconfirmed candidate |
| Cancellation | Propagate cancellation and publish nothing |
| Invalid learning material | Fail with its validation reason; publish nothing |

Failed/empty jobs do not replace prior complete candidates. The job never switches the active runtime. Parent/configuration checks still apply at adoption. Search intent/response records are not automatically replayed after an interruption. In-process cancellation cannot preempt arbitrary blocking plugin code.

## Inspect evidence and extend execution

The append-only search journal contains original trials, `material-input`, `material-review`, `learning-material`, separate learning/confirmation batches, full returned text receipts and stopping records. Candidate evidence binds material hashes, confirmation package hash and score comparison to the parent and candidate. Existing immutable task snapshots retain original acceptance; generated materials do not rewrite task packs.

Confirmation is used once per job. Reusing its outcomes to guide later jobs reduces its independence; reserve fresh final research tasks externally. There is no cross-job holdout-use enforcement, unlimited dataset loader or statistical quality claim.

`NativeSearchServices` accepts a [TrialExecutor](../trials.py). [IsolatedHarnessExecutor](../execution.py) runs task-owned Core tools/context using an injected `PreparedTrial`, startup/cleanup and verifier. Model calls retain the budgeted Provider. Register a services factory as `optimization-trial-services` before OPRO assembly, or inject it into `HostedTextOptimizer`. Benchmark adapters own dataset references, isolated initial state and official verification; Lab never imports Eval. Standard CLI packs still use single-turn text or restricted-function execution. [Original task experiments](../experiments/README.md) add a separate, explicitly confirmed path for single-step Harbor Terminal-Bench and SWE-bench task receipts. τ-bench is unsupported.

| File / entry | Responsibility |
|---|---|
| [workflow.py](workflow.py): `AutomaticWorkflow`, `AutomaticPolicy` | Preparation, feedback-driven strategy view, regression checks and confirmation |
| [registration.py](registration.py): `definition()` | Generic workflow declaration and host configuration |
| [Offline example](../../../../examples/optimization/automatic_text/README.md) | Model-generated exercises and explicit human adoption without network access |

```bash
.venv/bin/python -m unittest tests.lab.test_automatic_optimization tests.workflows.test_automatic_optimization -v
```

Offline checks establish control flow, isolation, scoring, budgets and review behavior. They do not establish real model improvement. No module-specific environment variables.
