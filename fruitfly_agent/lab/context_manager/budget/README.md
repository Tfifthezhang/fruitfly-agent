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
| `parameters.settings.trigger_ratio` | 0.75 | H policy, editable only with explicit grants |
| `parameters.settings.target_ratio` | 0.5 | H policy, editable only with explicit grants |

[Core defaults](../../../core/context/defaults.yaml) declare values once.
`ContextBudget` owns type and cross-field validation. `registration.py` declares
the Catalog parameters and controlled execution fields. `improvement.py` grants
only the two ratios through the existing parameter adapter. Candidate runs use
isolated Session/resources and the ordinary assembler. Model bindings own the window.
Remove `max_input_tokens` from component files and regenerate frozen execution
material containing that field.

## Calculate admission

Input capacity is the current role's model window minus the effective output
reserve for the request. System instructions, visible tools, messages and the
measurement margin count toward input occupancy. Reduction triggers at 75% by
default and aims for 50% of this capacity, including the margin. For a
1,000,000-token window with 131,072 reserved for output, capacity is 868,928.

Core measures the final request after transformations and hooks. Unknown
measurement or an output reserve that leaves no input capacity stops before the
Provider call. Measured overflow uses the bounded recovery path. Direct Core
callers must inject a `ContextMeter`; ordinary assembly and Lab role runners
install shared measurement automatically.

State-only maintenance can catch up while above the ceiling for at most
`max_context_recovery_attempts` preparation passes. Repeated state, no proposal,
failed commit or cancellation stops catch-up. Existing auxiliary time, page and
request limits still apply. State progress never claims request reduction.
No main request is sent until it fits. Large pinned inputs, tool groups or
signed replay can prevent reduction; this is an explicit failure, not permission
to truncate evidence or exceed model input capacity.

## Preserve execution identity

Effective conditions enter execution receipts and RuntimeManifest identities.
Current configuration applies on recovery; original Session records and their
historical digests are unchanged. Frozen component documents retain complete
values and include the declared default resource. Restricted children inherit
the parent reduction ratios even when their selected algorithm subset omits this owner.
Reduction summaries and memory updates also validate the shared ceiling against
their own model and output reserve.

Offline checks: `tests.core.test_context_budget`, `tests.lab.test_context_budget`,
`tests.run.test_parameter_defaults`, and `tests.providers.test_continuation`.
