# Ticket Triage Improvement

[Up: Improvement Examples](../README.md)

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
mkdir -p .fruitfly/improvement/task-packs
cp -R examples/improvement/ticket_triage .fruitfly/improvement/task-packs/ticket-triage
# Prepare experiment configuration before explicitly starting model work.
```

| Step | Action |
|---|---|
| 1 | Prepare the independent default Agent/model files and credentials. |
| 2 | Select `source: files` and the pack in the task document referenced by experiment `tasks`. |
| 3 | For persistent verification, set `scope: persistent` in the referenced comparison document and choose suitable independent phase times. |
| 4 | Run `fruitfly-agent-lab improvement check`, then explicitly `improvement run`; model calls may incur charges. |
| 5 | Inspect the linked candidate and evidence. `rsi run` performs verified adoption into its experiment copy. |

Search and live answers may incur model charges. Classification instructions can change general Agent behavior; inspect their scope before adoption.

## Check and compare

```bash
.venv/bin/python -m fruitfly_agent.lab.improvement.tasks.verification check examples/improvement/ticket_triage/pack.json
.venv/bin/python -m fruitfly_agent.lab.improvement.tasks.verification self-check examples/improvement/ticket_triage/pack.json
.venv/bin/python -m fruitfly_agent.lab.improvement.tasks.verification score examples/improvement/ticket_triage/pack.json --case holdout-001 --answer-file /tmp/ticket-answer.txt
```

These commands are offline. For independent testing, use the same model and six holdout inputs in fresh sessions, without expected labels. Keep all outputs and failures. A correct reference set does not establish model or improvement quality.

The public task-material API can add explicitly corrected examples to train without a model request. Do not move holdout cases into train. Search validation is a selection set, not independent evidence. See [Task packs](../../../fruitfly_agent/lab/improvement/tasks/README.md) and [Improvement](../../../fruitfly_agent/lab/improvement/README.md).
