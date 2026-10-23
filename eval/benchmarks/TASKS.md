# Select Benchmark Tasks

[Up: Benchmark Adapters](README.md)

Harbor tasks contain `instruction.md`, `task.toml` and an `environment/` definition.
Shared verifiers use `tests/test.sh`; separate verifiers own their tests in their
own image, usually built from `tests/`. Multi-step tasks can supply per-step
instructions and verification contexts. Optional `solution/` material is for task validation, not
Agent input. Instructions and initial files reach the Agent; the official verifier
checks resulting files or environment state and writes a reward.

| Benchmark | Dataset | Small selections |
|---|---|---|
| [Terminal-Bench 2.1](https://github.com/harbor-framework/terminal-bench-2-1) | `terminal-bench/terminal-bench-2-1` | `smoke`: `terminal-bench/fix-git`; `starter`: five exact tasks below |
| [Terminal-Bench 4.0.0](https://github.com/harbor-framework/terminal-bench/tree/v4.0.0) | `terminal-bench/terminal-bench@4.0.0` | ID `terminal-bench-4`; `smoke`: `terminal-bench/interleaved-vigenere` |
| [SWE-bench Verified](https://hub.harborframework.com/datasets/swe-bench/swe-bench-verified) | `swe-bench/swe-bench-verified` | `smoke`: `swe-bench/psf__requests-1142` |

## Select Terminal-Bench 4.0

Set `benchmark.id` to `terminal-bench-4` and `benchmark.variant` to `smoke` in the
[CLI request](../DEVELOPER_GUIDE.md#create-a-cli-request), then run `prepare`,
`check` and `run` using that request. The existing `terminal-bench` ID selects
2.1. The 4.0 smoke uses one CPU task with an independent verifier; it does not
establish full-dataset or GPU compatibility. Full `no_gpu` and `gpu` variants
include every resolved task, including GPU tasks. Prepare on a host satisfying
the selected tasks' resources. Real execution makes model requests and may incur charges.

## Run the Terminal-Bench starter

Set `benchmark.id` to `terminal-bench` and `benchmark.variant` to `starter` in the
[CLI request](../DEVELOPER_GUIDE.md#create-a-cli-request). Preparation resolves
tasks and checks images; execution calls models and charges can apply.

| Exact task name | Goal |
|---|---|
| `terminal-bench/fix-git` | Recover lost repository changes |
| `terminal-bench/log-summary-date-ranges` | Summarize log severities across date ranges |
| `terminal-bench/regex-log` | Match dates on lines with valid IPv4 addresses |
| `terminal-bench/cancel-async-tasks` | Implement bounded asynchronous execution and cancellation |
| `terminal-bench/fix-code-vulnerability` | Repair vulnerable code and describe the issue |

Preparation resolves the five exact names and freezes their local task paths.
Results must contain
each selected task exactly once per requested attempt. Smoke applies the same
coverage rule to its single task. These samples establish execution-path behavior,
not a representative benchmark score.

## Match images and task definitions

Task images alone do not contain all host-side instructions, configuration and
verifier material. Harbor resolves these through its dataset interface. Check
image tags, CPU architecture, disk, task resources, host/container connectivity
and model access. `no_gpu` performs no GPU preflight; it does not remove tasks
from the dataset. Harbor preserves individual resource and timeout declarations.

The Hub resolves unversioned datasets to their available revision during preparation;
`@version` selects the declared revision. Eval
freezes every selected task's content and records original/prepared hashes,
explicit setup diffs and image identities. Run consumes those local paths and
checks coverage for full datasets too. `task_directory` can use exported local
tasks without registry access. Keep preparation and Harbor job artifacts when
comparing runs. See [Eval results](../README.md#inspect-results).
