# Assessment

[Up: Improvement](../README.md)

Measure execution evidence independently of candidate editing. Model judges have
separate configuration and read-only contexts. No assessor activates a candidate.

| Entry | Responsibility |
|---|---|
| `inspection.py` | Independently constructed read-only model workspace |
| `metrics.py` | Incremental process counters; unobserved counts remain unknown |
| [Scorers](scorers/README.md) | Exact, restricted-function and separately configured model judgments |
| `registry.py` | Register factories without constructing or calling models |
| `configuration.py` | Completed-process settings and limits |
| `completed.py` | Granted completed evidence, independent assessment calls and persisted results |
| `completed_assessors.py` | Facts-only projection and optional model judgment/comparison |
| `aggregation.py` | Explicit weighted metrics; missing inputs yield unknown utility |
| `comparison.py` | Declared lexicographic objectives and required completeness |
| `selection.py` | Anonymous selection of existing executed outputs |
| `measured.py` | Injected selection policy, complete measured comparisons and incumbent ties |
| `verification.py` | Fixed selection/holdout comparisons and bound proof |
| `feedback.py` | Explicit development metric projection; private judgments stay private |
| `online.py` | Bounded online scheduling and optional control policy |
| `joint.py`, `promotion.py` | Complete task/collection aggregation and common-batch candidate comparison |
| `joint_process.py` | Optional cited next-seed judgment across completed development batches |

## Assess after execution

Hosted searches normalize [execution facts](../execution/README.md#record-execution-facts)
before assessment. Configure `parameters.process_assessment` in the selected
I feedback component; see the [system grammar](../../../runtime_spec/COMPONENTS.md).
The default empty assessor list
adds no judgment calls. This path does not require an online event stream.

| Assessor ID | Evidence and behavior |
|---|---|
| `execution-facts-v1` | Project known counters, scoped budget usage and termination; no model or inferred quality score |
| `completed-model-v1` | Read the task, immutable facts and explicitly granted full evidence; return cited judgments and optional metrics; compare executions for exploration |

`CompletedAssessorRegistry` registers factories and comparison/model requirements.
`CompletedAssessmentService` owns fresh instances, validates receipt identities and
evidence grants, and saves `process-assessments.json` plus journal references.
Judgments use the system's `models.roles.assessor` with no tools. Configured
`judgment_guidance` and `comparison_guidance` append task-independent instructions
to the fixed output protocols; they do not change the outer objective or proof. Model calls and comparisons share
`max_model_calls` (default 16) within each search and the root ledger. Each operation
has a `timeout_seconds` bound (default 120). Full granted input above 2 MB becomes
unavailable; it is not silently truncated or summarized. Binary content retains
metadata with no invented text. Private verifier material is never granted.

Optional errors/timeouts produce `unavailable`; exploration retains the incumbent.
With `required: true`, unavailable assessment/comparison ends search with
`assessment_unavailable` and cannot publish a persistent candidate. Root exhaustion
and cancellation propagate. No retry or repair loop conceals failed model output.

Completed and online judges require a final tool-free response. An intermediate
response is unavailable evidence even if its text happens to parse as valid JSON;
the model-call reservation remains charged.

Completed assessments supply editor evidence and final metrics to search stopping.
[Exploration](../strategies/README.md#choose-the-next-editing-seed) can consume them
without changing official measurements, final selection or independent assurance.
No universal process weights, task-specific diagnosis rules or quality threshold
are built in.

## Compare task sets

`assess_batch` averages attempts per task, normalizes each declared objective range
and direction, then applies `task-macro` or explicit `collection-macro` weights.
Raw rewards and policy IDs remain in leaf receipts. A genuine zero is valid;
missing, failed, out-of-policy or erroneous trials cannot shrink the denominator.
Incomplete coverage has no joint utility. Normalized utilities are development
objectives, not a new official benchmark score or proof of generalization.

`compare_candidates` requires identical task-set/batch identities, attempts,
conditions, aggregation and weights. Formal promotion requires strict configured
gain and optional collection nonregression. Intermediate small-batch results do
not compete directly with other batches. Selection uses every collection's own
selection split, falling back to its development tasks when absent.

Completed model assessors may implement `compare_batches` for exploration. Each
execution retains its own task instruction, facts and granted evidence. The
assessment allowance is shared across the entire search; failure and private-data
rules remain unchanged. No task-specific failure rules or automatic summaries
are added. See [Task sets](../task_sets/README.md).

## Observe online evidence

`AssessedRunner` wraps any execution backend. Fresh assessors consume immutable
committed events. `assessment_interval` schedules file-task assessments; 0 disables
it. The default `ProcessMetrics` observes every event even when judgments are
batched. Events persist independently of expensive judgment. Each assessment
records its exact evidence position, assessor, scope, status and supersession.
Final-only backends expose completion evidence, not fabricated live measurements.

`ModelAssessor` uses an injected model configuration and shared job services.
Requests reserve quota before invocation. It has no editing tools. A score does
not imply independence; development/private visibility and experimental splits
remain host-owned. There are no universal quality or process weights.

Online evaluation does not feed back by default. An explicit control policy may
request a supported action. Private, failed and terminal assessments do not cause
new runtime controls. Delayed controls can be rejected as stale. Assessment failure
is recorded separately from task failure; allocation exhaustion still propagates.
A required policy must reject incomplete assessment rather than infer success.

Historical proof and score records keep their assurance. No model weights are
trained. Source/code activation and arbitrary live replacement are unsupported.

```bash
.venv/bin/python -m unittest tests.lab.test_completed_improvement tests.lab.test_online_improvement tests.lab.test_evolution_policies
```

Process metrics count tool results (including errors/denials), model requests,
reported input/output tokens, and runner elapsed time. Missing/all-default token
receipts stay unknown. Tool-result counts do not prove tool bodies executed.
File events include immutable intermediate output references; a declared assessor
renderer can read those granted artifacts without reading live workspace state.
