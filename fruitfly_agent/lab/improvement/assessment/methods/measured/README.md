# Compare retained measurements

[Up: Assessment](../../README.md)

The default research `compare` consumes two native execute or newly imported Eval
batches, in before/after order. It makes no model requests and never activates a
candidate. Select `settings.method: model` explicitly for a model judgment.
The comparison component owns defaults in [defaults.yaml](defaults.yaml).

## Preserve the denominator

A `batch_manifest` declares planned task-attempt pairs and canonical task origins.
A `measurement` attributes a score, eligibility, official outcome, errors, time,
cost and provenance to its execution receipt. Both use the public
[observation contracts](../../../../../improvement/contracts/README.md).
Native execute emits these records directly; no conversion script is required.
A backend can attach `research/measurement.json` to declare official semantics.
A generic numeric objective alone does not declare pass/fail semantics.

Pair by canonical origin and attempt, never directory order or an implicit
intersection. Different plans fail unless `stages.compare.task_scope` explicitly
selects one of the two input batches, whose plan must be contained in both.
Excluded counts remain in the report. Historical imports preserve requested counts and unstarted tasks when selected
preparation and request are retained; otherwise they mark observed-only scope.
Neither case reconstructs original attempt identities from absent evidence.
Old untyped batches need reimport or an explicit `measured_policy`.

## Interpret the metrics

| Metric | Definition and missing-data rule |
|---|---|
| End-to-end pass rate | Mean per-task success fraction across planned attempts; recorded execution errors count as undelivered; absent or unknown outcomes make the estimate unavailable |
| Grading coverage | Eligible numeric grades / planned attempts; raw rewards on interrupted trials are excluded |
| Conditional pass rate | Confirmed successes / known official pass-or-fail outcomes; excludes execution errors and is never the headline denominator |
| Official score | Mean of available eligible numeric grades with count; paired difference reports paired numeric coverage separately |
| Reliability | Execution-error rate over observed runs, error types, status and outcome transitions |
| Retention and regression | Retained successes and known failures over former successes; missing follow-up outcomes make rates unavailable |
| Resources | Time, calls, execution-scoped token counters and USD with known counts and populations; incomplete totals remain unavailable |
| Tool error rate | Tool errors / tool attempts only when both counters cover every planned execution |
| Cost per success | Complete recorded USD / confirmed successes; unavailable with missing costs or outcomes or zero successes |

Example: 37 failed baseline tasks contain 6 valid failures and 31 execution errors.
If the candidate delivers 5 successes, 5 valid failures and 27 errors, its
end-to-end rate is 5/37; its conditional pass rate is 5/10 and grading coverage
is 10/37. These describe different questions. A missing receipt is never silently
removed or assigned a fabricated official score.

The 95% paired bootstrap resamples tasks, averaging repeated attempts inside each
task. The fixed seed and repetition count are frozen in the comparison policy.
Fewer than two tasks or incomplete outcomes yield no interval. This interval is
conditional on the selected tasks; it is not independent evolution evidence.

## Review provenance before claiming improvement

Per-pair checks cover primary metric, unit, direction, outcome policy, scorer,
material, execution conditions and initial state. Missing identities yield
`unknown`; differing identities yield `mismatch`. Historical importer evidence
and generic receipts do not invent verifier identity. Consequently an Eval report
can contain useful descriptive gains while its comparison conclusion remains
`insufficient`. Positive descriptive results do not prove a controlled improvement.
Changing executor models is permitted through the normal complete configuration;
report it as a changed experimental condition, not a mechanism-only effect.

With verified identities and complete outcomes, a negative gain is `worse`, zero
is `tied`, and a positive gain is `better` only when the interval lower bound
exceeds the configured minimum. A declared regression ceiling also applies.
Every other case is `insufficient`. No conclusion grants deployment permission.

## Read and export the report

One calculation produces `comparison.json`, `summary.md`, `metrics.csv` and
`tasks.csv` in the research bundle. JSON retains policy/input identities,
coverage, mismatches, unknowns, raw scores, per-pair receipts and metric counts.
CSV and Markdown render that same result. Known cost subtotals are not a bill;
research-role costs remain in their producer reports.

Keep development selection separate from an independent confirmation set. A
failed-only selection supports recovery claims on that subset, not whole-suite
improvement. Record selection before candidate execution; compare both conditions
on that selection and report exclusions when retaining a full baseline.

[Harness²](https://arxiv.org/abs/2610.14224) motivates reporting behavioral and
resource contrasts separately from task correctness. This implementation uses
attributed task outcomes and paired task intervals; it does not implement that
paper's benchmark or establish its results.

| File | Responsibility |
|---|---|
| `pairing.py` | Planned scopes, canonical pairs and provenance checks |
| `metrics.py` | Outcomes, coverage, transitions and accounting |
| `statistics.py` | Reproducible task-cluster interval |
| `policy.py` | Default report and conservative conclusion |
| `reporting.py` | Markdown and CSV projections |
| `__init__.py` | Explicit policy-based measurement API |

Offline checks: `tests.lab.test_comparison_reports`,
`tests.lab.test_measured_comparison`, `tests.workflows.test_small_batch_comparison`.
