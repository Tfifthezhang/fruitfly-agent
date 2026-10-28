# Independent Verification

[Up: Improvement](../README.md)

[__init__.py](__init__.py) implements `CaseMeasurements` and
`HoldoutVerification` behind the public `MeasurementSource` and
`VerificationPolicy` ports. These are optional capabilities, not prerequisites for
ordinary task execution or output selection.

Private task-package cases retain answers/checks. Their `TaskMaterial` projections
contain instructions only. A persistent candidate must pass fixed selection and
independent holdout comparisons after editing. Both baseline and candidate run
under the same root allocation. Original training cases must not regress. Selection and independent holdout
require aggregate strict gain and per-case nonregression. Missing/failed measurements reject publication. The host records
verification executions without returning answers to the editor.

Generation does not receive verifier objects or holdout instructions. Explicit
scored feedback is a separate choice for algorithms that need it. Verification
returns evidence-bound assurance; Run stores a pending candidate and Application
still owns adoption. Custom policies must declare their tasks, conditions,
independence, budgets and failure behavior.

Offline fake scoring establishes control flow, not actual model quality.
Checks: `tests.lab.test_improvement_pipeline`,
`tests.workflows.test_improvement_pipeline`.

Implementations now live in [Assessment](../assessment/README.md).
This module retains explicit compatible `CaseMeasurements` and
`HoldoutVerification` exports; it does not own a second verification engine.

## Validate delivery bundles

`delivery.py` supplies `DeliveryValidationRunner`, `DeliveryResult` and an explicit
`CommandDeliveryBackend`. The wrapper collects exactly the entrypoint, dependencies
and frozen inputs declared by the [delivery manifest](../execution/README.md#validate-declared-task-outputs).
It saves their hashes and a backend receipt with exit code, bounded stdout/stderr,
elapsed time, status and bundle identity. Missing dependencies, empty required
stdout, failed execution and unavailable validation reject that execution as a
selectable completed output; its diagnostic evidence remains available for editing.
Earlier validated outputs and immutable bundles remain intact.

A host selects the command's absolute executable; the manifest supplies no shell
or interpreter selection. The command backend creates a fresh temporary working
directory, supplies only declared files, clears environment variables, bounds time
and captured output, and retires the process group on timeout/cancellation. This
is a reproducibility check, not an OS security sandbox or proof of task correctness.
A backend requiring filesystem/network isolation must provide its own sandbox.
The kernel contains no language-specific delivery logic. No command backend or
production deployment is enabled automatically.

Backend admission requires `validate`, an `implementation_id` and a JSON
`configuration` dictionary. The command backend records the full declared command
in that configuration. Frozen preview identity and delivery receipts bind those
parameters, so changing the command cannot silently reuse an old identity.

Offline checks: `tests.lab.test_improvement_delivery` covers missing sidecars,
clean-directory execution, manifest admission and immutable receipts.
