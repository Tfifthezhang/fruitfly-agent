# Execution Definitions

[Up: Improvement](../README.md)

Register task execution through public metadata. Run consumes the definition;
frontends receive plain views and do not import a runner implementation.
There is no built-in local task executor.

## Register an execution definition

`ExecutionRegistry.register(ExecutionDefinition(...))` declares an ID, implementation,
H/S/I roles, capabilities, material discovery, preparation, construction, parameters
and cost notice. Discovery starts no models or task execution.

| Entry | Responsibility |
|---|---|
| [__init__.py](__init__.py): `ExecutionRegistry`, `ExecutionContext` | Registration and borrowed task/model/component/artifact capabilities |
| [episodes.py](episodes.py) | Role-neutral paired trials with injected episode factories |
| [File memory learning](../../context_manager/augmentation/memory/methods/file_memory/README.md) | H learning trials over isolated S updates |
| [tasks.py](tasks.py) | Task material, optional task-package scoring and holdout; requires an injected runner |
| [Experiment contracts](../../../improvement/contracts/experiments.py) | Requests, prepared material and stage ports |
| [Independent stages](../DEVELOPER_GUIDE.md) | Fixed-depth I comparison with an explicit episode/task backend |

`agent-task` is a material adapter, not an Agent executor. Supply
`StageBindings.runner(plan, components, artifacts, services)` when constructing
`RunApplicationFactory`. The factory must declare truthful `capabilities`.
Preparation rejects a missing backend before model work. The optional
[Eval adapter](../../../../fruitfly_eval/improvement/README.md) supplies executable
benchmark definitions through the same contracts.

Preparation validates component scope, typed parameters, source hashes and material
compatibility. `PreparedExecution` keeps private material out of editor requests.
File inputs are frozen bytes; task packages and experiment sources must still match
the preview. Construction returns `ExecutionPorts`: a runner, optional measurements,
verifier and selector, and an experience-retention policy.

## Bind execution explicitly

`StageBindings.executions` replaces the registry; `runner` supplies task
execution for definitions with `accepts_runner_override`. Its capabilities cannot
replace those of unrelated definitions. Stage factories, injected measurements and
verifiers remain independent; `stop_policy` replaces only stopping decisions.
Unknown IDs/parameters and incompatible capabilities fail before execution.

A backend owns tool selection, fresh configuration assembly, state isolation,
resource cleanup and attributable receipts. Registration does not provide an OS
sandbox. SSH, local and container environments retain their own permission and
lifecycle contracts. The material adapter does not filter tools or construct a
second Agent loop. Improvement applies independent phase times and observes usage
without model/tool/turn count quotas.

## Record execution facts

The shared [execution runtime](../../../improvement/execution/README.md) attaches
immutable `ExecutionFacts` to receipts. Facts bind task/material, harness, initial
state, conditions, termination, counters, usage and collected artifacts. Missing
diagnostics stay unknown; collection failure differs from confirmed absence.
Counters do not establish task quality. Keep original logs and omit opaque Provider
state from editor-facing trajectories. See [assessment](../assessment/README.md).

Backends implementing working memory should retain canonical trajectory separately
from the final projection and export memory diagnostics before retirement. These
artifacts grant no editing or activation authority. A runner supporting
`execution-setup` must apply fresh registered trial setups and own their resources;
unsupported runners reject the requirement.

## Schedule task batches

Shared `TaskScheduler` bounds concurrency, preserves result order and handles
cancellation/cleanup. `BatchEvaluator` builds fresh ports and independent phase
clocks for each leaf. Receipts bind task, harness, state and conditions. Reusing a
confirmed receipt within the same frozen attempt does not create a new sample.
Interrupted batches retain completed receipts and incomplete coverage. Source
failure differs from scored zero. See [task sets](../task_sets/README.md).

## Stream evidence and control a probe

A backend can expose `start`, an execution handle, committed events, scoped
`control` and `aclose` through the shared runtime. Final-only runners use
`CompletionOnlyRunner`; no intermediate measurements are invented. Managed handles
support scoped stop. Unsupported or stale control is rejected. Contracts for
checkpoint, fork and state transfer do not implement those capabilities.

[Online assessment](../assessment/README.md) reads committed evidence without
mutable Core access. Changes take effect at an implemented execution boundary;
changed I is rebound at the next editor invocation or generation.

## Validate declared task outputs

[deliverables.py](deliverables.py) defines `DeliverySpec` and `DeliveryBundle` for
output files, independently of harness `CandidateBundle` edits. The task adapter
accepts `delivery_manifest`, naming a frozen JSON input with `entrypoint`,
`dependencies`, allowed `inputs`, optional `arguments`, `timeout_seconds` (1–600,
default 30) and `require_stdout` (default true). Paths must be distinct and relative;
unknown or duplicate keys fail. Outputs must come from collected deliverables;
inputs must come from frozen material.

A manifest requires both a task runner and an explicitly supplied
`StageBindings.delivery_backend`. Task packages without file inputs reject it.
[Delivery verification](../verification/README.md#validate-delivery-bundles) owns
clean-directory execution, results and limits. No ambient file is an implicit
dependency and no delivery result authorizes production activation.

## Check offline

```bash
.venv/bin/python -m unittest tests.lab.test_execution_registration tests.improvement.test_research_service tests.experiments.test_stage_cli tests.eval.test_improvement
```

Fake Providers test contracts and orchestration. Real backend execution may call
models or start containers and requires an explicitly invoked experiment.

Execution owners can declare `material_snapshot`, `persistent_policy`,
`required_components` and `requires_runner_factory` for the generic registered
experiment source. Material declarations do not supply execution capabilities.
