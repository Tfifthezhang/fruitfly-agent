# Independent Verification

[Up: Improvement](../README.md)

[Assessment verification](../assessment/verification.py) owns `CaseMeasurements`
and `HoldoutVerification` behind the `MeasurementSource` and `VerificationPolicy`
ports. Private task cases remain excluded from generation. Independent fixed
comparisons bind publication eligibility to exact candidate and parent identities;
Application owns activation. See [Assessment](../assessment/README.md).

This module owns deliverable backends. It exposes no compatibility scoring imports.

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
