# Bound working context

[Up: Context Manager](../README.md)

Core enforces one working input budget for every reduction method and for runs
without reduction. The model catalog retains the actual model window.

## Configure the shared H policy

Select `H.context-budget: {default: true}` in the ordinary profile. Customize a
workspace component file through the existing configuration editor and `file`
reference. Disabling or omitting this component restores Core defaults; it never
disables final admission. The component changes shared conditions, not the
selected reduction method.

| Setting | Default | Ownership |
|---|---|---|
| `parameters.settings.max_input_tokens` | 65536 | User/host configuration; protected from candidates |
| `parameters.settings.trigger_ratio` | 0.75 | H policy, editable only with explicit grants |
| `parameters.settings.target_ratio` | 0.5 | H policy, editable only with explicit grants |

[Core defaults](../../../core/context/defaults.yaml) declare values once.
`ContextBudget` owns type and cross-field validation. `registration.py` declares
the Catalog parameters and controlled execution fields. `improvement.py` grants
only the two ratios through the existing parameter adapter. Candidate runs use
isolated Session/resources and the ordinary assembler; ratios cannot increase
the protected ceiling or bypass Core admission.

## Calculate admission

Working capacity is `min(max_input_tokens, model_window - output_reserve)`.
Input occupancy includes system instructions, visible tools, messages and the
measurement margin. Methods receive the remaining input allowance after margin;
the trigger and target ratios use that allowance. The default trigger is about
48K tokens, independent of a model's 1M capacity. Estimates remain heuristic
unless the Provider supplies exact counting.

After transformations, reduction and hooks, Core measures the final request.
Unknown measurement or excess working occupancy stops before a Provider call
with `context_budget_exhausted`. Physical model overflow retains bounded overflow
recovery. Direct Core callers must inject a `ContextMeter`; ordinary assembly
and Lab role runners install shared measurement automatically.

State-only maintenance can catch up while above the ceiling for at most
`max_context_recovery_attempts` preparation passes. Repeated state, no proposal,
failed commit or cancellation stops catch-up. Existing auxiliary time, page and
request limits still apply. State progress never claims request reduction.
No main request is sent until it fits. Large pinned inputs, tool groups or
signed replay can prevent reduction; this is an explicit failure, not permission
to truncate evidence or exceed the working ceiling.

## Preserve execution identity

Effective conditions enter execution receipts and RuntimeManifest identities.
Current configuration applies on recovery; original Session records and their
historical digests are unchanged. Frozen component documents retain complete
values and include the declared default resource. Restricted children inherit
the parent conditions even when their selected algorithm subset omits this owner.
Reduction summaries and memory updates also validate the shared ceiling against
their own model and output reserve.

Offline checks: `tests.core.test_context_budget`, `tests.lab.test_context_budget`,
`tests.run.test_parameter_defaults`, and `tests.providers.test_continuation`.
