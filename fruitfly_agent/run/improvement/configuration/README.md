# Research Configuration

[Up: Improvement host](../README.md)

`ResearchDocument` reads one editable `experiment.yaml`. `research`, `baseline`,
`roles`, `overrides`, `optimization`, `stages`, `evidence` and `next` express user
intent. `observed` is a generated view and never authorizes execution.

| File | Responsibility |
|---|---|
| `document.py` | Strict document parsing, stage settings and comment-preserving observation updates |
| `resolution.py` | Complete derived system configuration and owner-validated edit grants |
| `presentation.py` | Branch references and historical configuration summaries |
| `snapshot.py` | Redacted immutable captures, differences and complete candidate exports |

Paths resolve from this document, including `research.output_root`. A candidate
reference selects a complete exported system. Ordinary profile overrides merge
mappings recursively and replace lists/scalars; the shared Catalog validates the
result. Source configs and previously exported candidates remain unchanged.
`roles.executor` selects the executor in that complete system profile. Auxiliary
role selections affect only their requested phase.

Optimization defaults include enabled supported surfaces except File memory and
the three I roles. `include` overrides an individual owner's field grant;
`exclude` removes owners. `scope: explicit` starts from no grants. None of these
operations enables a disabled mechanism or bypasses owner validation.

Generated observations preserve authored bytes and comments. An advisory lock and
byte comparison prevent overwriting concurrent user edits. If the document has
changed, the stage result remains retained and `observed_updated` is false.
The generated section is informational; immutable run reports remain authoritative.
`observed.last_invocation` and `configuration/current.md` describe the last captured
invocation. Use `show` for the next invocation after editing the file. The positive
`research.history_entries` setting bounds the generated recent/reference lists;
`references.json` retains the complete branch reference index.

```bash
.venv/bin/python -m unittest tests.run.test_research_configuration tests.experiments.test_stage_cli
```

Import settings admit task-name lists and archive-relative path/hash supplements
through the existing strict research grammar. They are source adapter inputs;
`evidence.supply` configures role-wide limits. See the
[configuration owner](../../../experiments/CONFIGURATION.md#select-imported-evidence).
