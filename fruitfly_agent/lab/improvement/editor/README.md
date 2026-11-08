# Edit Candidates

[Up: Improvement](../README.md)

`AgentEditor` uses the shared [Agent runner](../../agents/README.md). It reads
[evidence](../evidence/README.md), discovers legal optimization targets on demand,
and changes only granted candidate paths. It has no Bash, production Session,
adoption operation or permission to alter field descriptions.

| Tool | Behavior |
|---|---|
| `catalog`, `search`, `read` | Navigate evidence and read attributable source spans |
| `list_targets`, `describe_target` | Load the frozen target index and field semantics |
| `write_file`, `delete_file` | Change candidate component files |
| `submit_candidate` | Validate the candidate and finish the editing invocation |

Each changed component supplies a reason, observed execution IDs and an
`expected_effect`: an observable behavior and evidence that could refute it.
Successful loading proves installation, not behavioral improvement.

The editor has one independent stage time, including evidence recovery and format
repair. There are no request, tool or turn quotas. Runtime failure ends the stage;
invalid submissions can be repaired within the same stage time. Completed earlier
executions survive a failed later proposal.

`improvement-editor` exposes
`parameters.instructions.{system,propose,reflect}`.
Owners validate instructions and experiment scope. I comparisons run fresh
fixed-I inner searches; instructions do not replace themselves during a call.

| File | Responsibility |
|---|---|
| `agent.py` | Editing mission and repair |
| `instructions.py` | Owner-described mutable instructions |
| `tools.py`, `submission.py` | Candidate operations and attribution validation |
| `generators.py` | Registered zero-or-one candidate generation |

Offline checks: `tests.lab.test_detached_editor`,
`tests.lab.test_improvement_configuration`, `tests.experiments.test_stage_cli`.

## Maintain I parameter defaults

[defaults.yaml](defaults.yaml) is the single default I instruction document.
Typed instruction constructors derive values from it. Isolated editors modify
`parameters.yaml` with a protected `role: I`; ordinary H/S task execution cannot
supply I acceptance. Frozen comparisons and verified activation retain the
existing I execution and recovery contracts.

## Inspect evidence coverage before editing

Editing guidance points to each execution's overview and coverage resources.
Inspect relevant originals through the shared reader before attributing a defect.
Missing files, partial indexing and unknown usage limit the supported conclusion;
they are distinct from demonstrated task failure. The editor cannot modify source
receipts or coverage to change an apparent outcome. See [evidence](../evidence/README.md).
