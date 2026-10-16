# Original Task Experiments

[Up: Improvement](../README.md)

Connect immutable benchmark task references and official execution receipts to the existing [automatic workflow](../automatic/README.md). Lab consumes an injected executor; it never imports Eval or owns containers. The built-in host changes the base prompt in H while fixing I and the initial S.

## Run a benchmark improvement job

1. Start a normal session with a configured model. Search and failed-task replay with independent confirmation bind on demand; no improvement configuration switch is required. Optional YAML can retain a custom failure processor or workflow policy.
2. Open `/improvement` and select **Start improvement → Benchmark tasks**. Choose Terminal-Bench's `starter` or a bounded CPU sample.
3. Inspect the task partitions, parent version, model allocation, trial budget, and deadline. Explicitly confirm **Start improvement**.
4. The same Application job downloads/freeze tasks, runs the baseline, prepares learning material, iterates candidates and confirms once. **It downloads tasks/images and calls model services.** Original tasks run in fresh official environments with their original verifier.
5. Use `/improvement → Review candidates` to inspect and explicitly adopt a confirmed result in a fresh session.

Selection/preview starts no task download or model calls. Configuration alone does not start improvement. A separate preliminary evaluation is not required; baseline, learning, candidate comparison and confirmation share one model/trial budget.

The terminal offers five-task CPU sets; the generic task preparation contract accepts 3–12 tasks. The Run host accepts 3–12 distinct tasks, sorted by dataset and task name. All but the last two form training, the next forms selection, and the last forms confirmation. A five-task set therefore splits 3/1/1. Selection is repeated during improvement; confirmation occurs once per job after generation stops. This small split demonstrates the mechanism, not statistical significance. There is no cross-job holdout-use ledger; reserve fresh final research tasks separately. A smoke task alone is insufficient.

## Inspect task evidence

| Contract | Contents / rule |
|---|---|
| `TaskReference` | Dataset, exact task name, source revision, complete instruction, material hash, verifier and environment identities |
| `EvidenceArtifact` | Kind, owned relative path and SHA-256 identity |
| `TaskRunEvidence` | Actual task/run, official score or unavailable status, output, artifacts, H/I/S, conditions, invocation usage and runtime/environment identities |
| `ExperimentTasks` | Nonoverlapping training, selection and confirmation references |
| `BenchmarkTaskSource` | Small immutable handles passed through the existing task interface; handles are not simplified benchmark tasks |
| `BenchmarkSearchServices` | Dispatch original handles to the official executor and derived exercises to their declared learning policy |
| `BenchmarkContext` | Frozen parent/tasks, baseline text, executor and explicit artifact capabilities |

Complete original task material stays outside algorithm generation. The independent [evidence projection](../failure_processing/README.md) sends only scored training instructions, output, feedback and attributed trajectory excerpts to the chosen failure processor. It retains the last six canonical messages, bounded to 1600 characters each, with source hash, line and truncation markers. It rejects instructions over 40000 characters instead of silently replacing the task. Full trajectories remain archived. Derived learning scores never replace the original official reward as the improvement metric.

Missing rewards, setup errors, cancellation and exhausted budgets are unscored. Infrastructure failures do not become invented zero-score learning examples. The executor verifies original task bytes before and after execution. Runtime receipts must match task, version, model allocation, conditions and usage. Effective instruction hashes and execution-environment identities must remain stable across repeated trials of each task.

## Freeze versions and invocation budgets

[System versions](../../algorithms/README.md) bind H execution mechanisms, I improvement strategy and S registered persistent material separately. Run freezes source files, configuration/catalog, artifact bindings and supported workspace text state before starting. Trial copies may change independently; production state is not updated by the experiment. Adoption rechecks the actual parent H/I/S, prepared candidate version, and experimental model/permission conditions.

| Parameter on `automatic-text-search` | Default | Behavior |
|---|---:|---|
| `external_trial_model_calls` | 24 | Reserve this complete allocation from the shared root model-call budget before starting each original task |
| `external_trial_timeout_seconds` | 1800 | Per original-task process deadline |
| `external_timeout_seconds` | 14400 | Whole benchmark improvement workflow deadline |

A validated invocation receipt releases unused allocation. Unknown, failed or cancelled external work retains its reservation. The isolated [Run trial host](../../../run/runtime/README.md) counts main and auxiliary Provider calls before execution and caps each output request. Improver, materializer, reviewer, derived exercises, original tasks and confirmation share the root budget. Provider-internal retries are opaque; invocation limits are not cumulative-token or monetary limits. Missing external token receipts remain unknown.

## Read artifacts and extend execution

| Workspace path | Material |
|---|---|
| `.fruitfly/improvement/task-sources/<id>/` | Prepared immutable original task set, material hashes and source cache; no Agent scores |
| `.fruitfly/improvement/experiments/<id>/experiment.json` | Origin, explicit task split, parent H/I/S, fixed conditions and outcome |
| `.fruitfly/improvement/experiments/<id>/source/` | Frozen runtime source and declared build inputs |
| `.fruitfly/improvement/experiments/<id>/runtime/` | Frozen profile and model catalog; no key values |
| `.fruitfly/improvement/experiments/trials/` | Independent task executions and attributable receipts |
| `.fruitfly/improvement/searches/` | Failure input, material review, learning, original comparisons, confirmation and budget records |
| `.fruitfly/artifacts/` | Content-addressed versions, modification sets, state/source snapshots and candidate text |
| `.fruitfly/improvement/candidates/` | Reviewed/adoptable candidate records |

Generic role comparisons use `ImprovementComparison` from [Contracts](../contracts/README.md). The built-in path uses the automatic original-task regression and confirmation rules. It has no I/S comparison implementation. `TargetRegistry` resolves only explicitly registered role/target/schema adapters; declaring a workflow/code/state change does not make it executable. [contracts.py](contracts.py) owns benchmark-specific host context. Temporary method selections bind the chosen host before task preparation and preserve the active default.

The Eval executor currently consumes single-step Harbor tasks from Terminal-Bench 2.0 and SWE-bench Verified. It requires a source checkout, Harbor, Docker and model access. Multi-step tasks, τ-bench, arbitrary Python plugin state, dynamic HTTP context, code/workflow changes and improvement of the improver or memory are unsupported. Built-in Markdown memory, skill files and local knowledge have registered initial-state snapshots. Live HTTP context rejects freezing. Custom plugins must explicitly register dependencies; text snapshots do not capture arbitrary heaps or external services.

The initial H and I identities both bind the same source snapshot; independent code-target comparisons are not implemented. Source hashes cover Python package files and declared build inputs. Receipts record Python/platform/package versions and reject changed environments across trials of a task. They do not pin transitive package downloads or prove a Docker image digest. Real container integration and model quality require separate online verification.

```bash
.venv/bin/python -m unittest tests.lab.test_experiment_contracts tests.eval.test_evidence tests.workflows.test_benchmark_improvement -v
```

These offline checks use normal Applications with fake Providers and an injected fake official executor. They establish the covered control flow and isolation, not real benchmark gains. No new environment variables.
