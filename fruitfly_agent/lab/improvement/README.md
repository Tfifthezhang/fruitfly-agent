# Improvement

[Up: Lab](../README.md)

Organize retained batch records, assess observations, propose configuration changes,
execute fixed candidates and compare results as separate research activities.
Each invocation performs exactly one stage. There is no automatic baseline/search
or multi-stage runner. Follow the [developer guide](DEVELOPER_GUIDE.md) and
[stage example](../../../examples/experiments/research-stage.example.yaml).

```bash
fruitfly-agent-lab improvement show --config experiment.yaml
fruitfly-agent-lab improvement check --config experiment.yaml
# Runs exactly next.stage; model/task stages may incur charges.
fruitfly-agent-lab improvement step --config experiment.yaml
```

The main configuration keeps each stage's inputs and controls together. It
selects explicit named batches, evidence, feedback and configuration origins.
Output-only history never selects work. Every stage retains its own
configuration snapshot; differences do not block using old records.

| Module | Responsibility |
|---|---|
| [Stages](stages/README.md) | Independent role/backend bindings over injected capabilities |
| [Evidence selection](evidence_selection/README.md) | Bounded detailed cases from complete compact summaries |
| [Organizer](organizer/README.md) | Readability, hierarchy, citations and source coverage |
| [Editor](editor/README.md) | Discover optimization signals and generate detached candidates |
| [Assessment](assessment/README.md) | Structured feedback and comparison; optional official observations |
| [Evidence](evidence/README.md) | Paged originals, search, directories and access receipts |
| [Components](components/README.md) | Owner adapters and authorized changes |
| [Targets](targets/README.md) | Text and retained-content surfaces |
| [Execution](execution/README.md) | Registered isolated task backends |
| [Task sets](task_sets/README.md) | Collections and batch execution settings |
| [Tasks](tasks/README.md) | Explicit task material and private acceptance partitions |
| [Materials](materials/README.md) | Frozen study material |
| [Verification](verification/README.md) | Independent proof; distinct from research continuation |
| [Experience](experience/README.md) | Separately attributed retained lessons |
| [Execution control](stages/control.py) | Explicit control policies; no automatic stage scheduling |

`editor/proposal.py` has no runner, selector or search engine. It validates a
proposal through `editor/validation.py`; historical batches enter through
`ResearchProposalRequest`, without synthetic scores or search evaluations.
Organizer and Assessor never acquire candidate write tools. They do not invoke
Editor or task execution to fill missing evidence.

## Select editable surfaces

Defaults include every enabled supported owner except `file-memory`, the three
I instruction roles and the I evidence-selection policy. Native tool instructions/parameters, `base_prompt`, current
context-policy fields, Skills and retained memory/skill libraries participate.
`stages.propose.optimization.include` sets an owner's field grant; `exclude` removes owners;
`scope: explicit` starts empty. Mechanism activation and edit permission remain
separate. Owner validators protect schemas, implementations, credentials and
inactive mode fields. A proposal is not independent verification or activation.

## Extend a stage

Use public [runtime contracts](../../improvement/contracts/README.md) and
[execution ports](execution/README.md). Runtime owns one-activity lifecycle;
Lab owns algorithms; Run owns configuration, Providers and persistence. Optional
Eval adapters belong to Eval and are wired by the outer entry point.
Concrete selectable methods remain under their owner's `methods/` directory.
Do not make one stage import and invoke another stage's service.

```bash
.venv/bin/python -m unittest tests.experiments.test_stage_cli tests.improvement.test_research_service tests.lab.test_organizer tests.lab.test_editor_execution
```

Offline fakes establish protocol behavior, not model quality or benchmark gains.
I prompt targets remain available for explicit proposal; automatic nested I
comparison/search is not an installed execution backend.

Historical Eval imports contain deterministic compact materials. The normal path
is import followed by assess or propose; model organize is optional. See
[bounded evidence](evidence/README.md#bound-an-investigation) for supply limits,
source references and explicit original supplements.
