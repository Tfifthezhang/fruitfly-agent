# Compare Evaluator Prompts

[Up: Improve Improvement Components](../../README.md)

[episodes.py](episodes.py) restores one frozen evaluator prompt candidate into
the existing fixed-I inner search. No separate orchestration loop is introduced.
The inner editor can change only the declared H/S components.

[verification.py](verification.py) retains the outer reference policy before
candidate construction and measures resulting task outputs against private checks.
The candidate evaluator has no access to expected answers, acceptance thresholds
or proof publication. Paired development/verification, phase times and one-use proof
rules remain owned by the parent runner.

Offline checks: `tests.lab.test_evaluator`, `tests.lab.test_improvement_configuration`
and `tests.workflows.test_editor_evolution`, `tests.workflows.test_evaluator_evolution`.
