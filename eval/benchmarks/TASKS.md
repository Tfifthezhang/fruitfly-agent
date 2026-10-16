# Run Public Benchmark Tasks

[Up: Benchmark Adapters](README.md)

Use `/improvement → Start improvement → Benchmark tasks` to select public tasks for iterative improvement. Each original task has its own container, session and official verifier. The same job prepares tasks and runs baseline/candidate comparisons. For standalone scores and reports, use the Eval CLI.

## Understand task material

| Benchmark | Public format | Verification | Built-in Eval support |
|---|---|---|---|
| [SWE-bench Verified](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified) | Dataset rows: `instance_id`, `repo`, `base_commit`, `problem_statement`, installation version and test material | Repository changes must pass issue and regression tests | Harbor-converted Verified tasks; smoke or full dataset |
| [Terminal-Bench 2.0](https://github.com/harbor-framework/terminal-bench-2) | Task directories: instructions, initial environment and files, resource configuration, verifier | Check files, code or environment state | Smoke, five-task starter or full dataset |
| [HumanEval](https://github.com/openai/human-eval) / [EvalPlus](https://github.com/evalplus/evalplus) | Function-level programming problems and tests; responses carry task IDs | Execute function tests | No built-in Eval adapter |
| [Original τ-bench](https://github.com/sierra-research/tau-bench/blob/main/tau_bench/types.py) | User identity, simulator instructions, reference actions and outputs; domain tools, rules and initial database | Check final database changes and required response content | No built-in Eval adapter |

SWE-bench's `patch` is the reference solution; `test_patch`, `FAIL_TO_PASS` and `PASS_TO_PASS` belong to evaluation material. Preserve these roles in experiments. A problem statement alone does not prepare the repository or dependencies. Original τ-bench instructions describe the simulated user, rather than serving directly as the assistant's initial prompt.

## Inspect a Harbor task

The [Harbor task format](https://harborframework.com/docs/tasks) packages executable tasks as directories:

```text
task-name/
├── instruction.md
├── task.toml
├── environment/
│   └── Dockerfile
├── tests/
│   └── test.sh
└── solution/
    └── solve.sh
```

Instructions describe the goal. Configuration declares resources and deadlines. Environment material prepares initial state. The verifier writes a numerical reward under `/logs/verifier/`. The optional reference solution validates the task and is not Agent input. Additional files and alternative environment definitions may be present. Harbor downloads selected task material when the job starts; these tasks are not converted into Improvement's small task packs.

## Run the five-task starter

Choose **Terminal-Bench → Starter batch · 5 CPU tasks** in `/improvement → Start improvement → Benchmark tasks`:

| Registry name | Work to observe |
|---|---|
| [fix-git](https://github.com/harbor-framework/terminal-bench-2/tree/69671fbaac6d67a7ef0dfec016cc38a64ef7a77c/fix-git) | Recover lost changes in the task's Git repository |
| [log-summary-date-ranges](https://github.com/harbor-framework/terminal-bench-2/tree/69671fbaac6d67a7ef0dfec016cc38a64ef7a77c/log-summary-date-ranges) | Count log severity across date ranges and write CSV |
| [regex-log](https://github.com/harbor-framework/terminal-bench-2/tree/69671fbaac6d67a7ef0dfec016cc38a64ef7a77c/regex-log) | Match dates on lines containing valid IPv4 addresses |
| [cancel-async-tasks](https://github.com/harbor-framework/terminal-bench-2/tree/69671fbaac6d67a7ef0dfec016cc38a64ef7a77c/cancel-async-tasks) | Implement bounded asynchronous execution and cancellation cleanup |
| [fix-code-vulnerability](https://github.com/harbor-framework/terminal-bench-2/tree/69671fbaac6d67a7ef0dfec016cc38a64ef7a77c/fix-code-vulnerability) | Repair code and write a vulnerability report |

These names were checked against Harbor `0.23.0`'s [registry](https://github.com/harbor-framework/harbor/blob/v0.23.0/registry.json). Its `terminal-bench@2.0` entries reference commit `69671fbaac6d67a7ef0dfec016cc38a64ef7a77c`. Runtime resolution still uses Harbor's versioned registry; this selector adds no source snapshot or image digest.

At that source version, each environment requests one CPU, `2G` memory and `10G` storage, without a GPU requirement. These are allowances, not measured RAM or download sizes. Image architecture, actual disk consumption, registry connectivity and model compatibility remain host checks. Difficult tasks can still fail or time out.

Interactive execution makes one attempt per task, runs one trial at a time and has a four-hour whole-job deadline. Task-specific setup, Agent and verifier deadlines still apply; Harbor owns task order. The runner passes five exact include filters and a five-task cap. Returned task names and attempt counts must match; missing, unexpected or duplicated attempts fail result validation. CLI requests can explicitly set other execution values.

## Prepare and inspect a run

Install the benchmark extra and start Docker Engine using the [environment guide](../DEVELOPER_GUIDE.md#prepare-the-environment). Enable the improver, failure processing and automatic workflow, save the intended model/harness configuration and start a session. Enter `/improvement`, select benchmark tasks and the starter, and confirm **Start improvement**. **Launching downloads tasks/images and makes real model requests that may incur charges.** Working container, registry and Provider connections are required.

Standalone Eval results live in `.fruitfly/eval/<evaluation-id>/`: `report.md`, `report.json`, parsed `trials/`, and Harbor artifacts with task sessions, events and setup/verifier logs. A completed report does not imply all tasks passed. Inspect infrastructure errors separately from failed tasks. See [artifact paths](../DEVELOPER_GUIDE.md#follow-execution-and-reports).

This selected exercise set is not a representative benchmark score or an improvement training/holdout split. Reports are not automatically ingested by the [automatic text workflow](../../fruitfly_agent/lab/improvement/automatic/README.md). Preserve original environment and verifier identities when deriving future learning material.

Direct improvement task material lives in `.fruitfly/improvement/task-sources/`; experiments, source snapshots, search journals and reviewed candidates use the [original-task improvement layout](../../fruitfly_agent/lab/improvement/experiments/README.md#read-artifacts-and-extend-execution).
