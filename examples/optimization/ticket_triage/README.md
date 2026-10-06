# Ticket Triage Optimization

[Up: Optimization Examples](../README.md)

Adapt active prompt text to a fixed SaaS support classification policy. This manually authored example is not customer data, a formal benchmark, or a measured comparison against human prompt engineering.

## Files

| File | Purpose |
|---|---|
| [pack.json](pack.json) | Schema 2 identity, direction, target compatibility, and policy |
| [cases.json](cases.json) | 8 training and 4 selection cases |
| [holdout.json](holdout.json) | 6 independent cases, excluded from search |
| [references.json](references.json) | Reference labels for material checks |
| [baseline.txt](baseline.txt) | Optional reference prompt |
| [results-template.md](results-template.md) | Blank record of actual results |

## Classification policy

Consider only current, real problems that still need action. Apply priorities in this order:

| Label | Condition |
|---|---|
| `P0\|SECURITY` | Active unauthorized access, data exposure, or abused credentials |
| `P1\|OUTAGE` | No active security incident; service unavailable or business requests failing |
| `P2\|BILLING` | Neither above; charge, refund, pricing, or invoice correction request |
| `P3\|HOWTO` | None above; question about using or configuring an existing feature |
| `P3\|OTHER` | Remaining requests, such as feature suggestions for a working service |

Resolved incidents, negated events, drills, and isolated keywords do not trigger escalation. Output one label only. Scoring normalizes case and whitespace, but not punctuation, explanations, or code fences.

## Install and use

From the project root, with a destination that does not exist:

```bash
mkdir -p .fruitfly/optimization/task-packs
cp -R examples/optimization/ticket_triage .fruitfly/optimization/task-packs/ticket-triage
.venv/bin/python -m fruitfly_agent
```

| Step | Action |
|---|---|
| 1 | Enable OPRO in Optimization and start a new session. |
| 2 | Record the active target hash; `baseline.txt` is not loaded automatically. |
| 3 | `/optimize` → **Start optimization** → select the installed ticket pack. |
| 4 | Review direction, model, cases, and budgets; explicitly start the paid search. |
| 5 | Review evidence and changes; save or confirm a new session. |

Search and live answers may incur model charges. Classification instructions can change general Agent behavior; inspect their scope before adoption.

## Check and compare

```bash
.venv/bin/python -m fruitfly_agent.lab.optimization.verification check examples/optimization/ticket_triage/pack.json
.venv/bin/python -m fruitfly_agent.lab.optimization.verification self-check examples/optimization/ticket_triage/pack.json
.venv/bin/python -m fruitfly_agent.lab.optimization.verification score examples/optimization/ticket_triage/pack.json --case holdout-001 --answer-file /tmp/ticket-answer.txt
```

These commands are offline. For independent testing, use the same model and six holdout inputs in fresh sessions, without expected labels. Keep all outputs and failures. A correct reference set does not establish model or optimization quality.

**Save a failed task** can add corrected real examples to train without a model request. Do not move holdout cases into train. Search validation is a selection set, not independent evidence. See [Task packs](../../../fruitfly_agent/lab/optimization/TASK_PACKS.md) and [Optimization](../../../fruitfly_agent/lab/optimization/README.md).
