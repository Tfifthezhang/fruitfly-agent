# FruitFlyAgent Engineering Rules

[Up: FruitFlyAgent](README.md)

**Build an interactive Agent harness on a stable Core, pluggable Lab, and Application lifecycle. Make algorithms usable through public interaction contracts. Keep Eval an optional external consumer.**

## Start here

| Before working | Action |
|---|---|
| Understand the task | Read the user's current request; keep changes within its scope. |
| Understand the project | Read this file, [Runtime architecture](fruitfly_agent/README.md), and affected module READMEs. |
| Prepare an edit | Read the affected source and tests in full; preserve unrelated user content. |
| Check project identity | Keep version `0.1`; protocol and data schema versions are independent. |

## Communicate

| Situation | Action |
|---|---|
| A question | Answer it before making implementation changes. |
| Feedback or analysis | State your assessment and its reason before describing changes. |
| A nontrivial design | Explain the problem, give a concrete example or short trace, then explain the solution. |
| Progress update | Report a finding, decision, or remaining uncertainty; avoid repeating the plan. |
| Delivery | State what changed, which checks ran and passed, and which external paths remain unverified. |

Use short, direct sentences. Define necessary jargon. Prefer tables for comparisons and concrete behavior over abstract summaries.

## Choose the correct owner

Follow the dependency table in [Runtime architecture](fruitfly_agent/README.md#modules). [Architecture tests](tests/architecture/README.md) enforce the boundaries.

| Do not | Use this path instead |
|---|---|
| Put a concrete algorithm or vendor special case in Core | Implement it in Lab or Providers through existing protocols, hooks, and callbacks. Extend Core only for a general runtime requirement they cannot express. |
| Put Lab logic in a Provider | Keep the adapter responsible for API messages, streams, capabilities, and errors; register the algorithm in [Lab](fruitfly_agent/lab/README.md#develop-an-algorithm). |
| Add algorithm-specific branches to Run or the terminal | Register a definition and installer in [Catalog](fruitfly_agent/lab/catalog/README.md); extend a generic host contract only when required. |
| Let a benchmark dictate runtime, configuration, lifecycle, or algorithm interfaces | Extend [Eval](eval/DEVELOPER_GUIDE.md#add-a-benchmark) as a consumer. Normal interaction must work without Eval. |
| Bypass boundaries with hidden imports, dynamic imports, or copied code | Use the owning module's public interface. |
| Restore a session using configuration alone | Verify artifact contents and the full manifest through [Run recovery](fruitfly_agent/run/README.md#recovery). |
| Leave shadow packages after a directory move | Update imports, examples, and tests; add compatibility only when explicitly chosen. |

## Protect the workspace

| Do not | Use this path instead |
|---|---|
| Initialize VCS, create commits/branches, or rely on VCS commands before the user enables it | Read files before editing, inspect changes directly, and use offline checks. |
| Make real model requests without an explicit request | Use fake Providers and validate configuration or construction offline. |
| Run paid examples merely to check documentation | Check example syntax and public validators; use the explicit [integration entry](tests/integration/README.md) only when requested. |
| Print or store real keys in source, docs, tests, prompts, sessions, or reports | Follow [Configuration](CONFIGURATION.md): key values in the secret environment, variable names in the model catalog. Never repeat a user-provided key. |
| Treat local state as source | Exclude secrets, caches, bytecode, sessions, results, and build products using the [release checks](CONTRIBUTING.md#build-and-publish). |

## Update documentation with the change

| Requirement | Action |
|---|---|
| Language and style | Write all documentation in English. Use task-oriented headings, concise sentences, and tables wherever they convey the information clearly. |
| Navigation | Link parent READMEs to child guides, add child backlinks, and cross-link related responsibilities. Keep guides in the existing tree; do not create `docs/`. |
| Module coverage | Give independent modules a README describing purpose, public entry points, behavior, relevant files, configuration/effects, limits, and offline checks. Let parents cover small directories. |
| Current state | Describe implemented behavior and limits. Do not create histories, changelogs, migration narratives, roadmaps, planning files, or design diaries. |
| Examples | Check imports, arguments, profile IDs, commands, and results against the implementation. Identify placeholders and network/cost requirements beside the operation. |
| Research sources | Cite the paper in the algorithm's README and state which ideas and capabilities are actually implemented. Keep project inspiration and upstream naming in top-level documentation and legal attribution. |
| Naming | Use FruitFlyAgent, `fruitfly_agent`, `eval`, `fruitfly-agent`, `fruitfly-agent-eval`, and Provider consistently. |
| Removed or renamed content | Use `rg` to find stale paths, names, commands, fields, and links; update all affected references without relocating obsolete explanations. |

| Changed area | Documentation to check |
|---|---|
| Structure, imports, exports, CLI | Root/runtime READMEs, affected guides/examples, packaging, and architecture/contracts |
| Model, key, or configuration fields | [Configuration](CONFIGURATION.md), Provider/module guides, `models.yaml`, and `.env.example` |
| Algorithm, protocol, or lifecycle | Owning module, runtime architecture, and affected configuration/examples; Eval only when it consumes the capability |
| Eval identity, artifacts, reports, or external effects | Eval guides, storage/CLI examples, and notices beside affected operations |

Update affected pages in the same change. Do not rewrite unrelated pages or duplicate another module's internal explanation. Document roles and release procedures are in [Contributing](CONTRIBUTING.md#write-code-and-documentation).

## Verify before delivery

| Change or failure | Required action |
|---|---|
| Observable behavior, public protocol, error, configuration, CLI, or boundary | Add or update tests for the changed public behavior. |
| Bug fix | Include a regression that reproduces the defect. |
| Contract failure | Fix implementation drift. Do not regenerate baselines, widen dependency allowances, delete assertions, or skip tests to pass. |
| Explicitly authorized contract change | Review callers and compatibility/rejection behavior; synchronize implementation, tests, and docs; explain the impact. |
| Documentation, comments, or formatting only | Check links, examples, and consistency. New behavior tests and the full suite may be omitted; explain why. |
| Main CLI or entry-point change | Run `.venv/bin/python -m fruitfly_agent --help`. |
| Eval entry-point change | Run `.venv/bin/python -m eval catalog --json`. |

Run relevant offline checks first. For behavior changes, run the full suite and resolve every failure before delivery:

```bash
.venv/bin/python -m unittest discover -s tests -t .
```

Keep default tests offline, deterministic, isolated, and fast. Use [Tests](tests/README.md) for group selection, shared fixtures, and online isolation. Coverage is an omission signal, not a completion target.

## Follow the detailed workflow when needed

| Task | Read and apply |
|---|---|
| Add an algorithm | [Lab development](fruitfly_agent/lab/README.md#develop-an-algorithm): select the contract; declare state/reset/recovery, injected dependencies, budgets, and failure/cancellation behavior. |
| Assemble resources | [Catalog assembly](fruitfly_agent/lab/catalog/README.md#assembly-contract): register ownership and test failed construction, startup, and cleanup. |
| Search or evolve text | [Optimization](fruitfly_agent/lab/optimization/README.md) and [RSI](fruitfly_agent/lab/rsi/README.md): keep generation, verification, and activation responsibilities separate. |
| Conduct a formal experiment | [Lab evidence requirements](fruitfly_agent/lab/README.md#test-and-evaluate) and [Evaluation reproducibility](eval/DEVELOPER_GUIDE.md#reproducibility-limits): fix hypothesis, baseline, principal variable, exact identities, repeats/seeds, budgets, metrics, failure rules, and raw evidence. |
| Use learning state in comparisons | Record initial state, data splits, update/reset rules, and sharing across conditions. Keep evaluation answers out of learning data; change prompt/scorer only as a declared research variable. |
| Prepare a release | [Build and publish](CONTRIBUTING.md#build-and-publish): inspect source/distribution contents and verify installed entry points outside the checkout. |

Offline tests and fake rewards establish covered behavior, not model quality or capability gains. Token estimates, synthetic summaries, and RuntimeManifest identities do not replace real quality evidence, source snapshots, or learning-state records. Optional researcher-maintained code snapshots do not authorize VCS use.
