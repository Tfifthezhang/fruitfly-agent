# Run WorkBuddy with the native Agent

[Up: Eval](../README.md) · [Operational recipe](../../examples/experiments/workbuddy/README.md)

`workbuddy-code` composes the official Code dataset with a separate WorkBuddy
controller environment. Its declared smoke task is
`api_contract-hard-openapi_params`. Preparation verifies that exact task exists;
no fallback selects another task or the full dataset. Actual smoke execution is
separately authorized and uses models and containers.

## Keep owners separate

| Owner | Responsibility |
|---|---|
| Benchmark declaration | Dataset identity, variants and official smoke selection |
| WorkBuddy source | Complete dataset layout, official normalization and outcome attribution |
| Isolated backend | The pinned controller, preparation, process execution and retirement |
| Native bridge | Complete frozen system configuration, Session, supervisor and logs |
| Providers | Model protocols, API/Go authentication, session headers and request policy |

The runner uses WorkBuddy's declared Harbor 0.18.0 in its own Python environment.
It does not change the Harbor 0.23.0 dependency used by existing benchmarks.
The same CLI request, prepared task selection and Improvement ports serve both.
There is no additional benchmark or model registry and no model-name dispatch.

## Configure the controller and machine

Use ordinary `eval-host.yaml` with a `backend.file` reference to an owner document:

```yaml
# Placeholders: replace paths and checksum before preparation.
checkout: /absolute/path/to/workbuddy-bench
python: /absolute/path/to/workbuddy-bench/.venv/bin/python
source_sha256: REPLACE_WITH_64_HEXADECIMAL_DIGITS
```

`RunnerSettings` resolves paths from that document. `runner_identity(checkout)`
hashes declared source, benchmark defaults, project metadata and lockfile; `.env`,
user jobs and results are excluded. Changed source, interpreter selection,
installed engine source or controller packages invalidate readiness.
The worker validates the actual installed Harbor version and required public
Agent/lifecycle interfaces. It does not install missing dependencies.

`task_directory` points at the **complete dataset root** containing `dataset.toml`,
`tasks/` and shared verifier resources. This differs from a flat Harbor task export.
Agent mounts, dependency assets, evidence capture and optional TLS model relay
retain their existing owner fields. Model aliases and secrets stay in normal
FruitFlyAgent configuration; the WorkBuddy `.env` is not imported.

## Prepare exact material

Tasks-only preparation freezes complete dataset bytes and inspects effective
resources through the isolated engine without starting containers or inference.
Full preparation freezes Agent material, dependencies and official environment
probes. WorkBuddy's user initialization is applied before probing a non-root
Agent or verifier. Selected request/collection names restrict environment probes;
an explicitly prepared subset cannot be used as an unrestricted full population.

Original datasets remain unchanged. Official CompositeVerifier/user normalization
runs on a derived copy and records its resulting identity and change counts.
Snapshots retain dataset-local plugins and tests; altered snapshots are rejected,
not repaired in place. External links and cache overlap are rejected. Arbitrary
host verifier patches are unsupported. Private scoring resources are not Agent or
Editor inputs.

## Execute and retain official evidence

The runner preserves official bench timeout/environment behavior and uses explicit
request attempts/concurrency with retries disabled. The native CLI consumes the
complete frozen H/S/I and model configuration. Subscription connections keep their
Provider request policy and receive per-execution host relay grants. Unix relay
communication directories are mounted per trial; socket permissions use the actual
Agent group without changing host ownership. This avoids requiring a host TCP
port on Linux. Rootless UID/GID mappings still need a real integration check. API models
retain the existing secret-environment path. No generic model configuration is
synthesized by this adapter.

Process progress, Ctrl+C, job timeout and `eval stop` use the common scoped
retirement mechanism. The WorkBuddy environment records exact session ownership;
cleanup is confirmed separately from task scores. No failed task is automatically
replayed. Retained artifacts use the shared Harbor archive format because the
underlying engine is Harbor; WorkBuddy-specific scoring is not added to compare.

Before each trial starts, a controller hook records canonical task origin,
attempt number, scorer identity and frozen comparison conditions outside the
Agent-writable log directory. Import preserves these original attempts. Official
rewards remain unchanged; errors with raw rewards remain ineligible. The same
attribution enters native execute measurements and imported batches.

## Interpret comparison and limits

Measured comparison consumes these standard observations directly. Model/budget,
material or initial-state differences remain visible. The frozen S configuration
participates in the initial-state identity; differing retained state can therefore
leave a controlled comparison mismatched. A positive descriptive gain does not
grant activation or establish unseen-task quality. Unknown historical provenance
is not reconstructed.

The registered scope is currently **Code v1.0**. Web, Office and Security are not
registered by this adapter. An official configuration requiring an independent
LLM judge is rejected rather than silently disabling its scoring. Actual engine,
container, rootless mapping, model entitlement and verifier compatibility require
separately authorized integration checks; offline fixtures establish contracts.

| File | Responsibility |
|---|---|
| `configuration.py` | Independent runner settings and source identity |
| `tasks.py` | Dataset snapshots and exact task population |
| `preparation.py` | Prepared material, normalization, probes and current readiness |
| `worker.py` | Public SDK operations inside the selected isolated environment |
| `environment.py`, `agent.py` | Thin official-environment and native-Agent composition |
| `runner.py` | Frozen job construction and common process lifecycle |
| `hooks.py` | Original attempt attribution before Agent execution |
| `results.py` | Official outcomes and measurement provenance |
| `templates/` | Installed owner-specific initialization inputs |

Offline checks: `tests.eval.test_workbuddy_tasks`,
`tests.eval.test_workbuddy_configuration`, `tests.eval.test_workbuddy_preparation`,
`tests.eval.test_workbuddy_runner`, `tests.eval.test_workbuddy_agent`,
`tests.eval.test_workbuddy_models`, `tests.experiments.test_workbuddy`.

References: [official WorkBuddy Bench](https://github.com/Tencent/workbuddy-bench),
[official scoring/configuration](https://github.com/Tencent/workbuddy-bench/blob/main/configs/README.md),
[installed-Agent interface](https://github.com/Tencent/workbuddy-bench/blob/main/configs/harnesses/HARNESS_AUTHORING.md).
This implementation preserves official dataset/plugin behavior and supplies a
native FruitFlyAgent bridge; it does not replace the official judges.

Task selection uses the exact local directory ID, for example
`api_contract-hard-openapi_params`. Preparation retains the official
`task.name`, for example `workbuddy/api_contract-hard-openapi_params`, separately
for engine results and attribution. The short name must match the directory ID.
Do not remove the organization prefix from official task files. Run preparation
again after updating the adapter.
