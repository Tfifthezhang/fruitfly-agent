# Maintain Task Research Context

[Up: Improvement](../README.md)

`ResearchLedger` records bounded, task-local observations, candidate hypotheses and
round experiments. It installs through [lifecycle hooks](../../../improvement/extensions/README.md).
`workflow/mechanisms.py` owns assembly and progress stopping. The independent kernel has no research schema or research policy.

| Data | Source and limit |
|---|---|
| Observations | Actual development execution receipts, with run, material, harness and conditions identities |
| Hypotheses | Validated candidate reasons; explanations remain model or generator claims |
| Experiments | Completed round observations; repeated trials remain separate evidence |
| Best known run | Official incumbent identity when supplied; no invented quality score |
| Next experiment | Declared guidance plus the most recent attributed entries |

The ledger persists immutable entry artifacts through the injected artifact port.
When supplied, the host `save_record` capability stores copies in the job's
`research/` directory. The editor receives a read-only `research.json` reference
before proposal. Retrieval selects recent entries up to the configured bound;
it does not infer missing evidence, automatically summarize logs or import private
selection/confirmation cases. Reading this context does not satisfy the separate
execution-evidence citation requirement.

## Configure and compare mechanisms

Set these fields under fixed experiment `search`. The
[experiment grammar](../../../experiments/CONFIGURATION.md) owns their position.
They are scheduling infrastructure and are outside Improvement edit grants.

| Group | Fields and defaults |
|---|---|
| `research` | `enabled: false`, `max_entries: 128`, `retrieve_entries: 8`, `guidance: ""` |
| `progress` | `patience: 0`, `failure_patience: 0`; zero disables that condition |

Research requires `1 <= retrieve_entries <= max_entries <= 256`; guidance has at
most 4000 characters. Progress fields are integers in `0..10000`.
Unknown fields fail. Every trial uses fresh mechanism instances; phase times, objectives and private verification remain fixed.

Progress conditions stop after consecutive unchanged incumbent rounds or failed executions. They establish neither convergence nor task success. An executed incumbent and immutable output artifacts survive unsuccessful later edits.

There is no automatic production S update, cross-task learning, arbitrary source
editing or activation. Default mechanisms are disabled. Register another hook or
stop policy to replace this bounded recent-history policy.

Offline checks: `tests.lab.test_improvement_mechanisms`,
`tests.lab.test_improvement_configuration`, `tests.workflows.test_editor_evolution`.
