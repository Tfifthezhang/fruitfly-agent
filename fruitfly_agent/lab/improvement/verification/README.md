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
