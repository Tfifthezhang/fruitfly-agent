# Indexed Skill Documents

[Up: Skill methods](../README.md)

H `skills` projects names, trigger descriptions and read locations. Its only menu
control is enabled/disabled. Reading bodies and relative text references uses the
ordinary read tool. A complete index remains readable when inline metadata exceeds
the budget. The loader never executes scripts, requests an interview or changes
host permissions.

| File | Purpose |
|---|---|
| [registration.py](registration.py) | Installation, state dependency and owner classification |
| [config.py](config.py), [defaults.yaml](defaults.yaml) | Protected source root, editable usage and projection budget |
| [parser.py](parser.py) | Bounded frontmatter parsing and directory rendering |
| [index.py](index.py), [algorithm.py](algorithm.py) | Snapshot index and idempotent context block |

Installed content belongs to the parent's [S library](../../README.md). Candidate
assembly regenerates metadata and resources from the same effective content.
Offline checks: `tests.lab.test_skill_catalog`, `tests.workflows.test_memory_skills`.
