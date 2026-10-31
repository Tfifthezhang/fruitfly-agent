# Assess Executions

[Up: Improvement](../README.md)

One read-only model Agent assesses completed executions and compares existing
results. It uses the shared [Agent runner](../../agents/README.md) and
[evidence access](../evidence/README.md). It cannot edit candidates or activate them.

| Instruction | Responsibility |
|---|---|
| `instructions.criteria` | Task-specific standards and applicable dimensions |
| `instructions.assess` | Single-run judgment and process diagnosis |
| `instructions.compare` | Common criteria, tradeoffs and incumbent retention |

Default dimensions cover task quality, reliability, resource efficiency,
progress efficiency, verification/evidence quality and completion efficiency.
These are model instructions, not separate assessor implementations. Saturated
objective scores can still produce process signals and modification hypotheses.

Results contain per-dimension judgments, reasons, uncertainty, source citations
and findings classified as process signals, hypothesis checks or optimization
directions. The host validates structure, identities and supplied citations;
it does not invent an aggregate quality score. Official measurements remain
unchanged. Unsupported or malformed judgment retains the incumbent.

`improvement-evaluator` exposes `parameters.instructions.{criteria,assess,compare}`.
Each instruction contains 1–16000 characters. I trials use a fixed outer reference
and independent checks; a candidate evaluator cannot authorize its own adoption.

Each assessment or comparison has its own evaluator time. There are no model-call,
tool-call or cumulative token quotas and no forced final request. Search and read
pages as needed. Missing evidence remains unknown; timeout is unavailable judgment.

| File | Responsibility |
|---|---|
| `evaluator.py`, `instructions.py` | Shared model judgment and editable instructions |
| `completed.py` | Completed feedback persistence and comparisons |
| `selection.py`, `measured.py`, `promotion.py` | Existing-run selection and objective conditions |
| `verification.py`, [Scorers](scorers/README.md) | Independent checks and declared objective sources |

Offline checks: `tests.lab.test_evaluator`, `tests.lab.test_completed_improvement`,
`tests.workflows.test_evaluator_evolution`.
