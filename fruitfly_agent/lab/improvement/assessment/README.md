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
These are model instructions, not separate assessor implementations. Measurements are observations alongside execution evidence. The editor owns
optimization signals and modification hypotheses.

Results contain per-dimension judgments, reasons, uncertainty, source citations
and findings classified as process signals, hypothesis checks or evidence limitations. The host validates structure, identities and supplied citations;
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
| `selection.py`, `measured.py`, `promotion.py` | Evidence selection and explicit objective-analysis helpers |
| `verification.py`, [Scorers](scorers/README.md) | Independent checks and declared objective sources |

Offline checks: `tests.lab.test_evaluator`, `tests.lab.test_evaluator`,
`tests.lab.test_evaluator`.

## Maintain I parameter defaults

[defaults.yaml](defaults.yaml) is the single default I instruction document.
Typed instruction constructors derive values from it. Isolated editors modify
`parameters.yaml` with a protected `role: I`; ordinary H/S task execution cannot
supply I acceptance. Frozen comparisons and verified activation retain the
existing I execution and recovery contracts.

## Assess incomplete archives

The evaluator receives available overview/coverage paths with execution metadata
and uses the same paged evidence reader as the editor. Coverage distinguishes
collection/index gaps from execution-diagnostic completeness. Instructions separate
setup failure, interruption, demonstrated incorrectness and unavailable outputs;
known token subtotals cannot establish a full efficiency comparison. Existing
uncertainty and citation validation remain authoritative. Missing evidence grants
neither a successful outcome nor an unsupported failure claim.

## Inspect rejected model responses

Before final JSON parsing, the evaluator freezes the exact response in the shared
artifact store and journals `evaluation-response`. A rejected result journals
`evaluation-rejected` with the response identity, precise validation error and
a diagnostic artifact containing the run IDs and supplied citation IDs. These
records preserve the input needed for explicit reprocessing without executing
tasks again. They do not accept malformed opinions or weaken citation checks.
Missing responses after interruption remain explicitly unavailable. The Agent receives precise rejection feedback and may repair within the same
invocation clock. `submit_assessment` and `submit_comparison` validate structured
arguments through the same strict protocol. An interrupted or exhausted invocation
records `evaluation-unavailable`. `responses.reprocess_response` explicitly
revalidates retained JSON offline against the original records and supplied citations;
it does not rewrite malformed output or request a model.

Default search selection always invokes the configured selector for multiple
completed results. Measurement absence, equality or magnitude does not bypass
that judgment. Numeric ranking helpers remain explicit analysis utilities, outside
the default research and search stage control.
