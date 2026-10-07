# Benchmark Adapters

[Up: Eval](../README.md)

Describe datasets, resources, preflight, Harbor jobs, and official results. Adapters do not own Agent runtime behavior or task verifiers.

| File | Responsibility |
|---|---|
| [base.py](base.py) | Descriptor and adapter protocol |
| [harbor.py](harbor.py) | Shared runner, progress, logs, and result parsing |
| [terminal_bench.py](terminal_bench.py) | Terminal-Bench 2.0 identity and fixed smoke task |
| [swe_bench.py](swe_bench.py) | SWE-bench Verified identity and smoke task |

The installed-agent bridge reports project version `0.1`, matching package metadata.

| Contract | Requirement |
|---|---|
| Identity | Unique benchmark ID, dataset/version, adapter version, and exact smoke task |
| Resources | Explicit variants, network surfaces, timeout, and backend constraints |
| Results | Official rewards, missing data, errors, and manifest mismatch handling |
| Progress | Job/Agent/trial events; no precise image preparation percentage |
| Installation | Existing Python/venv preferred; bounded fallback setup with preserved logs |
| Retries | Connection-only, before job creation; bounded attempts with all logs retained |

Register in [Catalog](../catalog.py). Full setup, diagnostics, and extension procedures belong to [Evaluation guide](../DEVELOPER_GUIDE.md). `FRUITFLY_EVAL_PACKAGE` selects explicit source or wheel installation material; see [Eval](../README.md#select-installation-material). Offline tests need no Docker; real jobs need the optional Harbor installation, Docker/Compose, registries, and model access.

```bash
.venv/bin/python -m unittest tests.eval.test_catalog tests.eval.test_harbor -v
```
