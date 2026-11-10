# Research Configuration

[Up: Improvement host](../README.md)

`ResearchDocument` reads one stage-oriented `.fruitfly/improvement.yaml`.
`research` and `baseline` identify the study and complete system profile.
Each `stages.<name>` owns its inputs, context, allowance, purpose, output alias and
attempt decision. `next` contains only `stage`. Loading never executes work.

| File | Responsibility |
|---|---|
| `document.py` | Validate all stage syntax and project selected allowances |
| `resolution.py` | Resolve proposal field grants through Catalog owners |
| `presentation.py` | Publish branch references and output-only history projections |
| `snapshot.py` | Redacted immutable captures, differences and complete candidate exports |

The Lab stage registry supplies descriptions, controls, required inputs, model
roles and external effects. Only selected-stage references resolve; future aliases
do not require running their producers during configuration inspection.
Paths resolve from this document. Model bindings and component customization stay
in the selected system profile. No inline profile override grammar is installed.

Publication leaves authored bytes and concurrent user edits untouched.
`configuration/observed.json` and `configuration/current.md` describe captured
history; `references.json` retains the complete branch index. Use `show` for a
preview after editing. Aliases cannot overwrite different output content.

See [research controls](../../../experiments/CONFIGURATION.md) for field syntax and
[the developer guide](../../../lab/improvement/DEVELOPER_GUIDE.md) for new-environment
validation and experiment execution.

```bash
.venv/bin/python -m unittest tests.run.test_research_configuration tests.experiments.test_stage_cli
```
