# Task Packs

[Up: Improvement](../README.md)

Define tasks, acceptance criteria, and fixed data splits for candidate search. The active target supplies the baseline; runtime configuration supplies the model, improver, and budgets.

## Prepare a pack

```text
my-task-pack/
├── pack.json          Identity, schemas, policy, direction, and file references
├── cases.json         Training and selection cases
├── holdout.json       Optional independent test cases
├── README.md          Task purpose and instructions
├── baseline.txt       Optional reference prompt; not loaded automatically
└── references.json    Optional reference answers; not supplied to search
```

| Material | Purpose | Search access |
|---|---|---|
| `pack.json` | Declare and validate the pack | Frozen metadata |
| `cases.json`: `train` | First input supplies diagnosis; all cases check regressions after generation | First input; answers/checks stay private unless an explicit feedback policy exposes them |
| `cases.json`: `validation` | Fixed baseline/candidate comparison after generation | No inputs or answers in editor workspaces |
| `holdout.json` | Manual testing or one automatic confirmation after generation stops | No content access through the editor |

`default_direction` is optional package metadata; the current panel uses its explicit
**Improvement guidance** field and does not automatically load that metadata.
Guidance does not change scoring. To measure brevity or reliability, the policy must define those metrics.

## Text example

`pack.json`:

```json
{
  "schema_version": 2,
  "id": "ticket-triage",
  "name": "SaaS ticket triage",
  "description": "Classify current incidents and mixed support requests.",
  "default_direction": "Use training feedback to improve classification. Return only a label.",
  "task_schema": "single-turn-text-v1",
  "target_schema": "text-v1",
  "compatible_targets": ["base_prompt"],
  "objective": {"policy_id": "normalized-exact-v1", "direction": "max"},
  "files": {"cases": "cases.json", "holdout": "holdout.json"}
}
```

`cases.json`:

```json
{
  "train": [{"id": "train-001", "input": "Production login keeps returning 503.", "acceptance": {"expected": "P1|OUTAGE"}}],
  "validation": [{"id": "validation-001", "input": "An order was charged twice.", "acceptance": {"expected": "P2|BILLING"}}]
}
```

`holdout.json`:

```json
{"holdout": [{"id": "holdout-001", "input": "The service works; correct the invoice name.", "acceptance": {"expected": "P2|BILLING"}}]}
```

Omit the holdout file and declaration when none is available. These cases illustrate format, not business quality.

## Format limits

| Field / concern | Contract |
|---|---|
| `schema_version` | 2 |
| `id` | Stable unique ID; letters, numbers, dots, hyphens, and underscores |
| `name` / `description` | Required; at most 120 / 500 characters |
| `default_direction` | Optional descriptive guidance; at most 500 characters |
| Schemas / targets | Registered task policy; `text-v1` target schema; nonempty compatible target list |
| `objective` | Registered `policy_id` and `direction=max`; no imports, commands, or scorer source |
| `files` | Required cases and optional holdout; distinct single-level JSON names inside the pack; no symlinks, escaping paths, `pack.json`, or `references.json` |
| Case fields | Required `id`, self-contained `input` (up to 4000 characters), and policy-validated `acceptance` |
| Training / selection | 1–12 cases each to search; empty arrays may be stored but cannot be searched |
| Holdout | Optional, up to 12; contents excluded from improver, search workspace, and snapshots |
| Maintenance metadata | Optional `tags`, `group_id`, `reason`, `source`; not model material by default |
| Metadata limits | 20 tags of 120 characters; group ID 120; reason 1000; source up to 8 text pairs, keys 80 and values 1000 |
| Entire declared material | At most 100 KB |
| Invalid material | Reject unknown fields, duplicate JSON keys/IDs/inputs, and cross-partition group leakage. |

Input deduplication uses Unicode NFC and trimmed whitespace; semantic overlap still needs review. A textual input does not reproduce files, tool state, or a complete interactive task.

`validate_pack` checks manifest fields, declared documents, policy/target compatibility, then cases in train/validation/holdout order, followed by the total size. Case checks preserve ID, policy projection, input overlap, group overlap, and metadata order. Training saves use the same acceptance-field rule before policy projection. Returned material has typed metadata and policy-defined case mappings; type annotations do not replace validation of raw JSON.

## Python function cases

Use `task_schema=python-function-v1` and `policy_id=python-function-tests-v1`:

```json
{
  "id": "train-add",
  "input": "Implement add_one(value), returning value + 1. Output only the function.",
  "acceptance": {
    "entry_point": "add_one",
    "tests": [{"args": [0], "expected": 1}, {"args": [-2], "expected": -1}]
  }
}
```

| Acceptance | Meaning |
|---|---|
| `entry_point` | Public function name, not prefixed with `_` |
| `tests` | 1–12 declarative calls; no executable assertions or test source |
| `args` / `kwargs` | Positional list and optional keyword arguments |
| `expected` / `raises` | Exactly one; allowed exceptions: ValueError, TypeError, KeyError, IndexError, ZeroDivisionError |
| `preserve_args` | Optional check that inputs were not modified |
| Values | JSON depth 8, 100 entries/container, strings 1000 characters, finite numeric magnitude up to 1e9 |
| Scoring | Passed checks / all checks per case; equal-weight mean across cases |
| Comparison | Distinguish booleans from numbers; numerical int/float equality; recursive list/dict comparison |

| Execution limit | Current policy |
|---|---|
| Process | POSIX, isolated `-I -S` Python, empty environment, temporary cwd |
| Code | AST allowlist: functions and approved expressions, loops, comprehensions, exceptions, built-ins, and container methods |
| Disallowed | Imports, top-level execution, files, network, processes, reflection, classes, and decorators |
| Time | 4 seconds wall-clock per case; CPU soft/hard 2/3 seconds |
| Memory | Linux address-space limit 256 MiB; no equivalent macOS claim |
| Size | Source 20000 characters; AST 3000 nodes; serialized result 10000 characters; feedback 1000 characters; verification 16000 characters |
| Isolation | Fresh globals per check; kill and reap on cancellation or timeout |

This restricted subset is not a general code sandbox or deployment backend. Task policy owns parsing and scoring; optional measured feedback exposes only permitted results to generation. Execution identity binds worker/scorer content hashes, interpreter version, and platform.

## Check and score offline

```bash
.venv/bin/python -m fruitfly_agent.lab.improvement.tasks.verification check examples/improvement/python_functions/pack.json
.venv/bin/python -m fruitfly_agent.lab.improvement.tasks.verification self-check examples/improvement/python_functions/pack.json
.venv/bin/python -m fruitfly_agent.lab.improvement.tasks.verification score examples/improvement/python_functions/pack.json --case holdout-001 --answer-file /tmp/function-answer.py
```

| Command / API | Result |
|---|---|
| `check` | Validate materials and search readiness. |
| `self-check` | Check reference answers for every case; default `references.json`, optional `--references`. |
| `score` | Score a saved answer file, up to 30 KB. |
| Exit status | 0 success/full score, 1 incomplete score, 2 invalid material or invocation |
| `load_pack(workspace, path, policies=None)` | Loaded policy projection, source hash, and file hashes |
| `validate_pack(manifest, cases=..., holdout=..., policies=None)` | Validate parsed data; the projection is not an on-disk manifest. |
| `await score_answer(workspace, pack_path, case_id, output)` | Score with the same public policy. |

No model requests. Python scoring runs restricted local functions. Passing reference answers only validates the task materials.

## Install and search

Copy the complete example to a destination that does not exist:

```bash
mkdir -p .fruitfly/improvement/task-packs
cp -R examples/improvement/python_functions .fruitfly/improvement/task-packs/python-functions
```

| Step | Action |
|---|---|
| 1 | Start a normal session; no improvement enable switch is required. |
| 2 | Open `/improvement`; choose **Task**, **Editable components**, and **Candidate generator**. Native packages use **Agent task execution**. |
| 3 | Review the package policy. **Verification** selects behavior or measured feedback; **Improvement guidance** supplies optional search hints. |
| 4 | Set **Effect scope** to persistent for independent verification and a publishable candidate; review the frozen preview and budgets. |
| 5 | Choose **Start improvement** and confirm the paid search; Cancel is selected initially. |
| 6 | Inspect the result and evidence before setting the next-session default or starting a new session. |

Selecting a pack changes one job, not the YAML or runtime manifest. `/improvement TEXT` prefills direction, not a path. Search only changes target text, not Python task outputs. See [Improvement](../README.md) for budgets, results, and retention.

Embedding hosts can register read-only sources with `TaskPackRegistration` via `RunApplicationFactory(task_pack_sources=...)`. The default CLI scans the workspace task-packs directory, not arbitrary examples or Session directories.

Catalog discovery skips hidden directories and directories without a `pack.json` entry. Invalid manifests, including dangling symbolic links, remain visible as errors and cannot be used for search on any supported Python version.

## Maintain training acceptance

Embedding hosts can use `Application.correction_tasks()` and
`save_training_task()` to supply a self-contained input and explicit acceptance.
These public material operations make no model requests and modify train only.
They retain source attribution, reject cross-partition overlap, require explicit
replacement for conflicting acceptance, and validate the whole-pack hash.
New train-only packs require independent selection cases before search.

The improvement menu has no correction form. Author packs directly or use the
explicit host API above. Ordinary chat does not create task packs or inferred answers.

## Frozen evidence and independent testing

| Concern | Behavior |
|---|---|
| Pack identity | Hash manifest and every declared material file, including holdout. |
| Preview | One-use token binds target, parent manifest, direction, policy, and material identity. |
| Material changes | Invalidate the preview before any Provider request. |
| Editor workspace | First training task and supplied execution evidence; no selection/holdout inputs or private checks. |
| Search feedback | May contain policy-authorized acceptance facts; not all acceptance material is secret from feedback. |
| Holdout | Send only each input in a new empty session with the same model, save all responses, then score offline. |

Persistent [Improvement](../README.md) requires nonempty independent holdout. Verification privately freezes its cases and compares baseline/candidate after editing. Scorer answers and holdout instructions never enter generation. Task-local selection requires no scoring policy.

Host services exclude holdout contents from generation and material review; this is not a filesystem sandbox for arbitrary Python plugins. Confirmation is once per automatic job, not a guarantee of independence across repeated jobs. No automatic adoption is performed.

| Example | Purpose |
|---|---|
| [Python functions](../../../../examples/improvement/python_functions/README.md) | Function behavior and restricted scoring |
| [Ticket triage](../../../../examples/improvement/ticket_triage/README.md) | Exact-label classification |

```bash
.venv/bin/python -m unittest tests.lab.test_task_packs tests.lab.test_pack_format tests.lab.test_coding_tasks tests.workflows.test_unified_packs
```
