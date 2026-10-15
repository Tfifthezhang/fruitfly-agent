# Failure Processing

[Up: Optimization](../README.md)

Convert scored training failures into learning material. Methods are independently selectable from the search algorithm. They do not change original tasks, scoring policy, runtime text, or candidate adoption.

## Choose a method

| Catalog ID | Method | Model roles |
|---|---|---|
| `failure-replay` | Retain failed inputs and acceptance, with their observation provenance | None |
| `failure-distillation` | Generate smaller or varied exercises, validate their structure, and request a separate model review | `materializer`, `material_reviewer` |

Both methods are disabled by default and occupy the **Failure processing** selector under Optimization. Enable one alongside [Automatic text search](../automatic/README.md). Importing `definitions()` only constructs declarations; assembly makes no model requests.

The model method can choose the original task policy or either registered built-in learning policy: exact-text answers and restricted Python function checks. A learning exercise can therefore have a different type from its source task. No scorer source, arbitrary command, import path, or deployment instruction is accepted from generated material.

## Follow the material contract

| Value | Contents |
|---|---|
| `FailureExample` | Original `TaskCase` and matching, scored training `TrialObservation` |
| `LearningTask` | Derived or replayed case, source case identity, method, review, learning policy and execution identity |
| `LearningMaterial` | Immutable collection of 1–12 distinct learning tasks from one method |
| `FailureProcessor.process(failures, services, policy=..., limit=...)` | Prepare material using injected generation, journal and cancellation capabilities |

`failure-distillation` returns tasks in this model-output format:

```json
{
  "tasks": [{
    "source_case_id": "sha256:SOURCE_CASE_HASH",
    "policy_id": "python-function-tests-v1",
    "input": "Implement add_one(value), returning value + 1.",
    "acceptance": {
      "entry_point": "add_one",
      "tests": [{"args": [0], "expected": 1}]
    }
  }]
}
```

`SOURCE_CASE_HASH` is a placeholder replaced with an authorized failed training case identity. Omitting `policy_id` selects the source policy. Existing task-pack schema 2 remains unchanged; this generated document is an intermediate learning artifact, not a replacement task pack.

Generation receives bounded original instructions, acceptance, actual output, score and feedback. Complete examples are selected within the shared generation input bound. The exact input projection is recorded as `material-input`. Generated source IDs must belong to that projection. Unknown fields, policies, duplicate cases and invalid acceptance are rejected before review.

Each generated exercise receives a separate `material_reviewer` call. A malformed review or a batch with no accepted exercises stops material preparation. Accepted reviews are recorded and tied to the exercise. **Model review is fallible and qualifies learning material only.** Generated answers and tests are not independent quality evidence. The workflow requires improvement on fixed original tasks and independent confirmation before publishing a candidate. It also rejects learning inputs overlapping original selection or confirmation inputs.

## Configure and extend

| Parameter | Default | Effect |
|---|---|---|
| `materializer_profile` | Empty | Use the active Provider, or explicitly bind another catalog profile |
| `material_reviewer_profile` | Empty | Use the active Provider, or explicitly bind a separate reviewer profile |

Defaults use the same Provider in distinct roles; this is not independent model diversity. Both roles share the search's model-call budget and output/time limits. The original scorer remains fixed. Generation does not establish whether the observed failure has the hypothesized cause.

Implement `FailureProcessor`, supply an explicit implementation ID and a Catalog definition providing `failure-processing`, and install it as `FAILURE_PROCESSOR_COMPONENT`. Methods consume only authorized training observations. Persist analysis as attributed evidence, and declare state/reset/recovery, injected dependencies and effects. The built-ins are stateless between jobs; unknown interrupted calls are not replayed. Ordinary conversation corrections and other weak feedback sources are outside this implementation.

| File | Responsibility |
|---|---|
| [models.py](models.py) | Public immutable material and processor contracts |
| [processors.py](processors.py) | Replay and model generation/review |
| [registration.py](registration.py) | Independent Catalog choices and optional model binding |

```bash
.venv/bin/python -m unittest tests.lab.test_failure_processing tests.workflows.test_automatic_optimization -v
```

Checks use fake Providers and temporary material; they do not demonstrate learning or model gains. No module-specific environment variables.

## Project original execution evidence

[projection.py](projection.py) provides `EvidenceProjection`: only authorized scored training runs can be projected. It retains complete bounded instructions, score/feedback/output, parent/condition identities and attributed excerpts of canonical messages. Full trajectories remain owned artifacts; verifier files and configuration metadata do not enter generation. `FailureExample.material` carries this source evidence into both distillation and independent material review. Exercise tasks can have a different declared policy from the original task. See [Original task experiments](../experiments/README.md).
