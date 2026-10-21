# Select Benchmark Tasks

[Up: Benchmark Adapters](README.md)

Harbor tasks contain `instruction.md`, `task.toml`, an `environment/` definition
and `tests/test.sh`. Optional `solution/` material is for task validation, not
Agent input. Instructions and initial files reach the Agent; the official verifier
checks resulting files or environment state and writes a reward.

| Benchmark | Dataset | Small selections |
|---|---|---|
| [Terminal-Bench 2.1](https://github.com/harbor-framework/terminal-bench-2-1) | `terminal-bench/terminal-bench-2-1` | `smoke`: `terminal-bench/fix-git`; `starter`: five exact tasks below |
| [SWE-bench Verified](https://hub.harborframework.com/datasets/swe-bench/swe-bench-verified) | `swe-bench/swe-bench-verified` | `smoke`: `swe-bench/psf__requests-1142` |

## Run the Terminal-Bench starter

Set `benchmark.id` to `terminal-bench` and `benchmark.variant` to `starter` in the
[CLI request](../DEVELOPER_GUIDE.md#create-a-cli-request). Actual execution downloads
tasks/images and calls models; charges can apply.

| Exact task name | Goal |
|---|---|
| `terminal-bench/fix-git` | Recover lost repository changes |
| `terminal-bench/log-summary-date-ranges` | Summarize log severities across date ranges |
| `terminal-bench/regex-log` | Match dates on lines with valid IPv4 addresses |
| `terminal-bench/cancel-async-tasks` | Implement bounded asynchronous execution and cancellation |
| `terminal-bench/fix-code-vulnerability` | Repair vulnerable code and describe the issue |

The runner passes five exact filters and a five-task cap. Results must contain
each selected task exactly once per requested attempt. Smoke applies the same
coverage rule to its single task. These samples establish execution-path behavior,
not a representative benchmark score.

## Match images and task definitions

Task images alone do not contain all host-side instructions, configuration and
verifier material. Harbor resolves these through its dataset interface. Check
image tags, CPU architecture, disk, task resources, host/container connectivity
and model access. `no_gpu` performs no GPU preflight; it does not remove tasks
from the dataset. Harbor preserves individual resource and timeout declarations.

The Hub resolves a dataset to its available revision; Eval records the dataset
name and preserves Harbor's resolved job configuration and logs. Keep those
artifacts when comparing runs. See [Eval results](../README.md#inspect-results).
