# Improvement Runtime

[Up: Improvement](../README.md)

Bind methods to registered targets and run searches through shared services. This package does not define paper-specific stages or grant production activation authority.

| Entry | Responsibility |
|---|---|
| [selection.py](selection.py): `MethodSelection` | Discover compatible methods offline and bind a method for one job |
| `MethodBinding` | Borrow runtime dependencies; register owned construction resources with `own` |
| [host.py](host.py): `HostedTextImprover` | Freeze text problems, construct root services, report progress and return proposals |
| [workflow.py](workflow.py): `run_search` | Shared result, target and cancellation boundary for ordinary and controlled searches |
| `ImprovementWorkflow` | Explicit role/target/policy comparison and optional exact-version adoption for embedding hosts |
| [services.py](services.py) | Root budgets, model operations, trials and journal |
| [reporting.py](reporting.py) | Evidence-backed reports and usage receipts |
| [confirmation.py](confirmation.py) | Freeze independent cases and confirm one selection winner without further generation |

## Select a method

Catalog definitions may attach a [MethodDefinition](../methods/README.md). Discovery checks the target role/schema, declared runtime dependencies/conflicts, execution capabilities and available host binding without calling a strategy factory or Provider. Discovery omits methods with incompatible target roles or schemas before checking runtime requirements. Compatible methods lacking dependencies or capabilities remain visible with reasons. The standard Run host exposes H text/workflows, registered S retained documents and I policy adapters. Other unregistered bindings remain unavailable even if a method advertises those roles.

A per-job binding retains the active runtime. With no configured host, a lazy default borrows the active model and task catalog; method discovery constructs no search strategy. It borrows their model and execution services, creates separate search state, and uses normalized method parameters. Auxiliary model profile changes require configuration and a new session. A text binding can reuse the configured automatic workflow policy and processor; it does not share a live search.

Binders must register newly owned resources with `binding.own` before another construction step can fail. Failed binding closes registered resources. Completed and failed jobs release their temporary bindings. Remaining preview bindings close with the runtime; runtime cleanup continues after individual close failures. Borrowed Providers and target objects must not be registered as owned resources. Text binders are synchronous and must not start work.

Run preview receipts bind the chosen host, its implementation/parameters, target, tasks and parent H/S/I. Execution consumes one receipt and rejects changed method identity before requests. Method discovery alone does not prove code/state execution or activation support.

## Execute and compare

Methods own proposal order, evidence interpretation and stopping decisions. `run_search` uses the same root services for ordinary searches and optional controllers; original-task experiments enter through the same text host. The [automatic controller](../automatic/README.md) implements original-task regression and independent confirmation. Its scientific acceptance rules are not replaced by a generic search score.

`ImprovementWorkflow` is a separate version-comparison embedding contract, not a second built-in search algorithm. It requires explicit target preparation and comparison capabilities. The standard host does not claim generic S or arbitrary I code activation. `NativeSearchServices.for_target` borrows the same root budget, cancellation and usage ledger for isolated inner trials.

`HostedTextImprover.completion()` supplies an optional `SearchCompletion` with the final report and journal identity even for empty, failed or cancelled searches. It does not change the `TextImprover.search` return contract. Missing or unmeasured values stay unknown.

Search state is job-local. Interrupted model work is recorded but not automatically replayed. Cancellation returns no proposal. Runtime bindings are not a filesystem sandbox. Model/tool operations may incur cost; listing methods and validating parameters do not.

`MethodBinding.text_host(..., confirm_on_holdout=True)` enables shared host-owned confirmation. Preview and execution reject absent or changed holdout before model work. The strategy receives only train/selection; the host selects one winner, tests baseline and candidate once, and rejects missing measurements or any per-case regression. Budget exhaustion and cancellation cannot publish an unconfirmed candidate. This is independent of optional automatic material preparation. Reusing a holdout across multiple jobs still weakens its independence.

```bash
.venv/bin/python -m unittest tests.lab.test_improvement_selection tests.lab.test_improvement_roles tests.workflows.test_improvement_methods tests.workflows.test_automatic_improvement
```
