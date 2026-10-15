# OPRO

[Up: Optimization](../README.md)

Generate text candidates from a frozen objective and previously scored solutions. OPRO is a Lab optimization method; it returns candidates and search evidence without production adoption authority.

## Research basis

OPRO (Optimization by PROmpting) comes from Yang et al., [Large Language Models as Optimizers](https://arxiv.org/abs/2309.03409v3), Sections 2 and 4. An optimizer model proposes solutions from a task description and previously scored solutions; each new result becomes feedback for subsequent rounds.

| Paper idea | FruitFlyAgent implementation |
|---|---|
| Scored optimization history | Bounded valid candidates, ordered so the best appears last |
| Natural-language objective and examples | Frozen direction and authorized training examples |
| Generate, evaluate, repeat | Baseline evaluation, JSON-array proposals, deduplication, target validation, and train/selection scoring |
| Prompt optimization | `base_prompt` and `skill-catalog.guidance` text targets |
| Published experiments | Not reproduced; no GSM8K/BBH gains or general improvement claims |

## Use the method

The algorithm entry point is `from fruitfly_agent.lab.optimization.opro import OproOptimizer`. Its `search(problem, services)` implements the shared [Optimizer contract](../search.py). The package also exports `definition()`, which returns a fresh Catalog definition with OPRO parameters, effects, and its installer. The built-in Catalog explicitly collects this definition; importing the package does not register it or start work.

The mechanism is `opro`, with implementation identity `opro-text-v2`; it is disabled by default. Follow [Start a search](../README.md#start-a-search) to select a target, task pack, model, and budget. The installer uses the [shared text assembly helpers](../registration.py) and performs no search, file writes, or model requests.

| Concern | Behavior |
|---|---|
| Targets | `text-v1` snapshots; target adapters own meaning and legal changes |
| Required capabilities | Injected `evaluate`, `complete`, and `history` services |
| Parameters | `rounds`, `batch_size`, and `history_limit`; shared call limits and model settings are documented in [Optimization parameters](../README.md#parameters). |
| History | Local to one search; retain scored baseline and complete candidates, select a bounded view by objective utility |
| Proposals | JSON array of new strings; reject duplicates and invalid target text |
| Proposal failure | Record the error and continue within the round budget |
| Budget exhaustion | Return only complete candidates with `budget_exhausted` |
| Cancellation | Propagate cancellation; the shared host does not publish a candidate |
| State and recovery | No internal persistent state; the host records evidence and does not replay unknown paid requests |
| Results | At most three distinct candidates, ordered by selection score; the host projects and stores the preferred result |

Search calls the configured Provider and may incur charges. Shared trial services run isolated single-turn, no-tool evaluations; they do not measure a complete interactive Harness. Selection validation is reused during search. Independent verification and adoption belong to the host and optional [RSI coordinator](../../rsi/README.md).

The optional [automatic workflow](../automatic/README.md) supplies derived learning cases and fixed original selection cases through the same search contract. Its `candidate_evaluated` callback may stop generation at the first eligible candidate; it then performs original-task regression checks and separate confirmation. Ordinary OPRO retains its configured round limit. Independent [failure processors](../failure_processing/README.md) do not live inside OPRO. Learning scores remain feedback; candidate ranking uses original selection scores.

This package exposes no target for modifying its own strategy. Prompt constants are implementation details, not runtime artifact bindings. It performs no model training and has no module-specific environment variables.

## Files

| File | Responsibility |
|---|---|
| [__init__.py](__init__.py) | Public `OproOptimizer` and `definition` entry points |
| [optimizer.py](optimizer.py) | Candidate generation, history selection, deduplication, and result ordering |
| [prompts.py](prompts.py) | Proposal instructions and frozen-problem rendering |
| [registration.py](registration.py) | Method-owned parameters, effects, and installer definition |

## Check offline

```bash
.venv/bin/python -m unittest tests.lab.test_search tests.lab.test_catalog tests.workflows.test_optimization -v
```

Fake Providers verify prompt contents, ordering, failures, budgets, and interactive adoption. They do not establish real quality improvements.
