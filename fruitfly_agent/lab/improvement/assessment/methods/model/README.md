# Judge Granted Execution Evidence

[Up: Assessment](../../README.md)

`algorithm.py` implements `ModelEvaluator`, exported by the assessment package.
`defaults.yaml` owns its I prompts and initial evidence presentation settings.
Catalog, typed instruction/settings constructors and actual calls share this file.

The method reads evidence and may delegate through an explicit research host.
Every supplied execution needs dimension judgments under common comparison criteria.
The submission validator rejects unread citations and unavailable execution choices.
Rejected output is retained for diagnosis; repair shares the invocation deadline.
No task execution, candidate writes or activation authority is granted.

| Setting | Default | Meaning |
|---|---|---|
| `output_preview_characters` | 2000 | Per-run initial output span and its exact citation |
| `task_preview_characters` | 2000 | Maximum task excerpt in initial input |
| `minimum_input_characters` | 1000 | Floor for initial presentation size |
| `input_characters_per_token` | 2 | Initial text allocation estimate from available context |
| `task_input_divisor` | 3 | Fraction reserved for task text |

All settings are positive integers <= 24000. The character estimate is at most four
per token and the task divisor is at least two. These estimates do not replace the
shared pre-request measurement. Full task/output records remain behind paged reads.

Customize an I component with the ordinary `file` reference. Frozen exports retain
all settings and prompts. Candidate grants admit instruction fields only. Changing
schema guidance never weakens the host's schema or evidence checks. I adoption
still requires independent verification; offline fakes establish no quality gain.

Offline checks: `tests.lab.test_evaluator`, `tests.run.test_parameter_defaults`.
