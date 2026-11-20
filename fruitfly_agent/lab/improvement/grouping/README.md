# Compose one feedback group

[Up: Improvement](../README.md) · [Run an experiment](../../../experiments/README.md#compose-one-feedback-batch)

The independent `group` stage receives one frozen research batch. It publishes
a narrow `batch.json` and a separate research receipt, `grouping.json`. Bundle
consumers receive the narrow batch. The receipt records membership and the
composition settings.

| Component setting | Behavior |
|---|---|
| `method: fixed` | Select the list at `stages.group.position` from authored `stages.group.members`. Include distinct task IDs from the pool. |
| `method: random` | Partition the pool deterministically in seed-dependent order. Repeat with another position for another group. |
| `batch_size` | Positive group size. An incomplete group is marked in the receipt. |
| `seed` | Integer controlling the random partition. |

Set the component ID and implementation to `improvement-grouping`, with role
`I`. Put component settings below `parameters.settings`. The default fixed
method accepts one task per position. All retained attempts for selected tasks
are carried into the output batch.
For exact attempt membership, write a fixed member as `{task_id: example,
run_ids: [run-1]}`. Each listed receipt must belong to that task in the pool.

Offline checks use `tests.lab.test_research_grouping` and
`tests.experiments.test_stage_cli`.

The `failure`, `text` and `trajectory` methods choose neighbors of a seed-ordered
anchor by overlap in source outcome classes, description terms and action
signatures respectively. The `matched` control prioritizes similar outcome
classes and action/attempt counts. The `diverse` control minimizes the largest
similarity to current members. These positions may produce overlapping groups.
All methods publish the same feature representation for a given frozen pool.
Feature coverage includes missing event indexes. Descriptive associations and
action signatures establish composition criteria.
