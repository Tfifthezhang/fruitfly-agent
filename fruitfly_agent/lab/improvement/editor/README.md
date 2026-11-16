# Edit Candidates

[Up: Improvement](../README.md)

`AgentEditor` uses the shared [Agent runner](../../agents/README.md). It reads
[evidence](../evidence/README.md), receives bounded owner descriptions and discovers remaining target details on demand,
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
repair. Evidence supply, request-space checks and any selected delegation controls also apply. Runtime failure ends the stage;
invalid submissions can be repaired within the same stage time. Completed earlier
executions survive a failed later proposal.

`improvement-editor` exposes
`parameters.instructions.*`: system/propose/reflect, navigation and submission,
component/direction labels, evidence recovery, repair and candidate-tool guidance.
Owners validate instructions and experiment scope. I comparisons run fresh
fixed-I inner searches; instructions do not replace themselves during a call.

| File | Responsibility |
|---|---|
| [Workspace method](methods/workspace/README.md) | Editing mission, repair and complete owner defaults |
| `instructions.py` | Owner-described mutable instructions |
| `tools.py`, `submission.py` | Candidate operations and attribution validation |
| `generators.py` | Registered zero-or-one candidate generation |

Offline checks: `tests.lab.test_detached_editor`,
`tests.lab.test_improvement_configuration`, `tests.experiments.test_stage_cli`.

## Maintain I parameter defaults

[defaults.yaml](methods/workspace/defaults.yaml) is the single default I instruction document.
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

Repair retains the exact authorized resources, component descriptions, current
candidate files and supplied citations. It shares the original cumulative reading
allowance rather than granting a new investigation budget. A format error does
not make retained observations disappear. Evidence supply and context request
limits remain separate from the overall editing deadline.

`parameters.settings.target_page_entries` and `max_target_entries` control the
optimization-target directory. Values are positive integers with default <= maximum
<= 100. They are configurable and frozen with the component, but protected from
ordinary candidate grants. `AgentEditor(..., options=...)` consumes these controls;
`settings=...` remains the separate shared evidence configuration.

When supplied organization guides contain findings, each changed component must
reference existing `issue_ids` as well as original `evidence_ids` and a testable
`expected_effect`. Local issue IDs are accepted only when unambiguous. Use `<guide-artifact-id>/<issue-id>`
when multiple supplied guides share a local ID. Reading derived
findings alone never supplies the original execution citation required for edits.

Prepared hosts preserve configured context mechanisms and scoped archive
readback. When [work products](../../agents/work_products/README.md) are enabled,
roles checkpoint progress and can submit an exact saved JSON revision through
the same final validator. Rejected fields can be patched without retransmitting
the complete document. Direct Lab embeddings without a prepared host retain
minimal execution and record `role-runtime-mode`; they do not inherit ambient
configuration or claim an installed context policy.

The `submit_candidate` tool accepts `issue_ids` in each change reason. Tool and
text submissions use the same finding association checks. A finding reference
does not replace the required execution evidence. The Core tool execution
regression lives in `tests.lab.test_editor_execution`.

## Submit an explicit decision

[schema.py](schema.py) supplies one schema for tool and text submissions.
[decision.py](decision.py) validates intent separately from component identity.
Submit `reasons` plus a `decision` with `kind`, `explanation`,
`baseline_applicability`, optional `issues` and `required_materials`.

| Decision kind | Behavior |
|---|---|
| `candidate` | Actual component changes; each referenced issue is selected in the decision |
| `retain_baseline` | No changes; explain why the available evidence does not justify editing |
| `needs_evidence` | No changes; name relative material paths needed to investigate further |

Each issue decision contains `issue_id`, `disposition` (`selected`, `rejected`,
`deferred`) and `explanation`. Explicit candidate decisions select every issue
used by edit reasons. Requests for materials grant no additional read authority.
`baseline_applicability` explains the relationship between historical execution
and current component values; unavailable historical state stays unknown.

Changed legacy text submissions without a decision retain their supplied edit
reasons and mark applicability as unreported. Empty submissions require an explicit
decision. The built-in generator returns no new candidate for retain/needs-evidence;
`stop` remains an independent workflow control. Independent stages publish
`decision.json`; custom generators without decisions are marked `not_reported`.

Read deterministic `context/statistics.json`, discover organization indexes through
`catalog`, and inspect a bounded issue and contrasting cases before broad searches.
Per-execution summaries are also available under `context/summaries/` without
expanding detailed grants. Derived findings do not establish causal truth.

`parameters.settings.max_repair_attempts` bounds separate format/evidence repair
invocations (default 3). Like directory presentation settings, it is configurable
but protected from candidate instruction grants. Repairs retain the draft, exact
authorized sources and original cumulative allowance. Exhaustion is a runtime
failure, never an implicit retain-baseline decision.
