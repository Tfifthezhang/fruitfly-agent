# Task Packs

[Up: Optimization](README.md)

Define tasks, acceptance criteria, and fixed data splits for candidate search. The active target supplies the baseline; runtime configuration supplies the model, optimizer, and budgets.

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
| `cases.json`: `train` | Generation feedback | Yes |
| `cases.json`: `validation` | Repeated candidate selection | Yes; not independent validation |
| `holdout.json` | Manual testing after search | No content access through search services |

`default_direction` describes desired changes; it does not change scoring. To measure brevity or reliability, the policy must define those metrics.

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
| `default_direction` | Optional; at most 500 characters; prefill only |
| Schemas / targets | Registered task policy; `text-v1` target schema; nonempty compatible target list |
| `objective` | Registered `policy_id` and `direction=max`; no imports, commands, or scorer source |
| `files` | Required cases and optional holdout; distinct single-level JSON names inside the pack; no symlinks, escaping paths, `pack.json`, or `references.json` |
| Case fields | Required `id`, self-contained `input` (up to 4000 characters), and policy-validated `acceptance` |
| Training / selection | 1–12 cases each to search; empty arrays may be stored but cannot be searched |
| Holdout | Optional, up to 12; contents excluded from optimizer, search workspace, and snapshots |
| Maintenance metadata | Optional `tags`, `group_id`, `reason`, `source`; not model material by default |
| Metadata limits | 20 tags of 120 characters; group ID 120; reason 1000; source up to 8 text pairs, keys 80 and values 1000 |
| Entire declared material | At most 100 KB |
| Invalid material | Reject unknown fields, duplicate JSON keys/IDs/inputs, and cross-partition group leakage. |

Input deduplication uses Unicode NFC and trimmed whitespace; semantic overlap still needs review. A textual input does not reproduce files, tool state, or a complete interactive task.

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

This restricted subset is not a general code sandbox or deployment backend. Task policy owns parsing and scoring; OPRO only consumes scores and permitted feedback. Execution identity binds worker/scorer content hashes, interpreter version, and platform.

## Check and score offline

```bash
.venv/bin/python -m fruitfly_agent.lab.optimization.verification check examples/optimization/python_functions/pack.json
.venv/bin/python -m fruitfly_agent.lab.optimization.verification self-check examples/optimization/python_functions/pack.json
.venv/bin/python -m fruitfly_agent.lab.optimization.verification score examples/optimization/python_functions/pack.json --case holdout-001 --answer-file /tmp/function-answer.py
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
mkdir -p .fruitfly/optimization/task-packs
cp -R examples/optimization/python_functions .fruitfly/optimization/task-packs/python-functions
```

| Step | Action |
|---|---|
| 1 | Enable Text optimizer / OPRO and start a new session. |
| 2 | `/optimize` → **Start optimization** → select the pack. |
| 3 | Supply direction, or accept the pack default. |
| 4 | Review target, cases, policy, model, budgets, and execution notice. |
| 5 | Explicitly confirm the paid search; default selection is cancel. |
| 6 | Review results and choose whether to save or activate. |

Selecting a pack changes one job, not the YAML or runtime manifest. `/optimize TEXT` prefills direction, not a path. Search only changes target text, not Python task outputs. See [Optimization](README.md) for budgets, results, and retention.

Embedding hosts can register read-only sources with `TaskPackRegistration` via `RunApplicationFactory(task_pack_sources=...)`. The default CLI scans the workspace task-packs directory, not arbitrary examples or Session directories.

Catalog discovery skips hidden directories and directories without a `pack.json` entry. Invalid manifests, including dangling symbolic links, remain visible as errors and cannot be used for search on any supported Python version.

## Save a failed task

| Action | Behavior |
|---|---|
| `/optimize` → **Save a failed task** | Select from up to 20 completed canonical text tasks. |
| Complete the input | Supply all context needed to reproduce it. |
| Supply acceptance | Expected text, or policy-specific declarative JSON for an existing Python pack. |
| Confirm | Append to train only; no model request or automatic search/adoption. |
| Same input and acceptance | Idempotent save |
| Changed acceptance | Explicit replacement confirmation |
| Cross-partition overlap | Rejected |
| Read-only pack | Confirm a workspace copy; preserve the source. |

The new-pack form creates text packs; developers prepare Python manifests. Editing uses a single-writer lock, expected whole-pack hash, and precommit checks. Existing saves atomically replace only the cases file; new packs publish a whole directory. Add independent selection cases before searching a train-only pack.

## Frozen evidence and independent testing

| Concern | Behavior |
|---|---|
| Pack identity | Hash manifest and every declared material file, including holdout. |
| Preview | One-use token binds target, parent manifest, direction, policy, and material identity. |
| Material changes | Invalidate the preview before any Provider request. |
| Search snapshot | Frozen train/selection and execution evidence; no holdout contents. |
| Search feedback | May contain policy-authorized acceptance facts; not all acceptance material is secret from feedback. |
| Holdout | Send only each input in a new empty session with the same model, save all responses, then score offline. |

Host services exclude holdout contents; this is not a filesystem sandbox for arbitrary Python plugins. Automatic holdout execution and adoption gates are unsupported.

| Example | Purpose |
|---|---|
| [Python functions](../../../examples/optimization/python_functions/README.md) | Function behavior and restricted scoring |
| [Ticket triage](../../../examples/optimization/ticket_triage/README.md) | Exact-label classification |

```bash
.venv/bin/python -m unittest tests.lab.test_task_packs tests.lab.test_pack_format tests.lab.test_coding_tasks tests.workflows.test_unified_packs
```
