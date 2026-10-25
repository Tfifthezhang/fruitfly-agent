# Scorers

[Up: Assessment](../README.md)

`policies.py` owns normalized exact scoring and restricted Python function policy
validation. `python_worker.py` executes only the documented function subset in an
isolated POSIX subprocess. Task packages still own material format and partitions;
[task policy imports](../../tasks/scoring.py) remain compatible public imports.

`model.py` supplies `ModelAssessor`: a separately configured tool-free model
judgment with injected rendering, instructions and root-budgeted services. Its
strict metrics JSON is validated; provisional judgments do not establish success.
The caller declares evidence visibility and scoring meaning.

Function worker, scorer source, interpreter and platform identify executable
scoring conditions. Worker cancellation kills and reaps the process. Restrictions
are not a general code sandbox. Model judgments can incur charges; rule/function
tests use no credentials or network.

```bash
.venv/bin/python -m unittest tests.lab.test_coding_tasks tests.lab.test_pack_format tests.lab.test_evolution_policies
```
