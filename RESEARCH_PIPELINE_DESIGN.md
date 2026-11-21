# Design grouped evidence and GEPA proposal experiments

[Project](README.md) · [Runtime architecture](fruitfly_agent/README.md) · [Improvement](fruitfly_agent/lab/improvement/README.md)

**Scope:** research protocol and design rationale, not an operational capability reference. Grouping, GEPA reflective proposals and measured comparison have implementations described in the [current stage guide](fruitfly_agent/lab/improvement/DEVELOPER_GUIDE.md). Experimental choices and expected research outcomes below are not runtime guarantees. Use the owning module guides for available settings and limits. This document authorizes no execution; FruitFlyAgent remains version `0.1`.

## 1. Define the objective and current scope

Support one shared Harness candidate from multiple task trajectories with inexpensive Flash-class models. Make task grouping, evidence supply, evidence organization, proposal, execution and comparison independently testable. Preserve the single-task case as a batch of size one.

The research question is whether changing which task feedback enters a proposal improves transfer to tasks outside that proposal's sources. It is distinct from improving the organizer, choosing better prompts, or running a more powerful search algorithm.

GEPA is an additive, explicitly selected method within the existing proposal/editor capability. The `propose` stage, native `AgentGenerator`, workspace `AgentEditor`, existing grants and candidate output contracts remain available. Ordinary configurations keep the native method as their default. Selecting GEPA does not replace these owners, narrow the native method's edit surface, or require other methods to adopt GEPA input/output conventions.

| In this implementation scope | Outside this implementation scope |
|---|---|
| Independent task-grouping stage | Automatic eval–group–organize–propose–execute loops |
| Group-scoped material selection and lossless permitted trajectory readback | Combee and its aggregation/controller mechanisms |
| Bounded organization and reliable partial-result handoff | Full GEPA optimization, candidate population, Pareto search or crossover |
| GEPA package used for one reflective instruction proposal | Weight training, learned task encoders or online task routing |
| Deterministic comparison beside model-assessor comparison | Dataset onboarding, acquisition or platform comparisons |
| Frozen provenance and research accounting | Automatic production adoption or activation |

The project already supplies immutable candidates, component grants, independent research stages, execution receipts, source-attributed evidence readers, model roles and optional benchmark adapters. Extend those owners. Do not add a second Agent loop, parameter registry, persistence ledger or benchmark-dependent Core interface.

## 2. Preserve the evidence from the TB2.1 audit

Archive examined: `/Users/tfifthefrank/fruitfly-agent issue/tb21-rsi-qwen38-20261119`.

The audit covered 89 original results, converted trajectories and capture manifests, with targeted native Sessions, request receipts, verifier outputs and research Sessions. It did not read every captured file or prove candidate quality.

| Observed fact | Design requirement |
|---|---|
| 89 imported trajectories preserve 6,731 message records, but 87 tasks have excerpt truncation | Separate outline completeness from body completeness; make complete permitted bodies directly retrievable |
| 337 tool arguments and 526 texts are truncated in the reading projection | Never treat reading later pages of that projection as recovery of removed text |
| Native Sessions contain 3,107 thinking blocks, 187 compaction records and 41 image blocks absent from the default native-source reading projection | Record available extensions and their grants; do not require all extensions in every proposal |
| 34 of 46 timeout trials have collected file entries | Distinguish capture, import, authorization, supply and understanding |
| Six error-status trials have raw reward 1; only two trials lack a raw reward | Preserve raw measurement separately from execution eligibility and declared acceptance |
| Per-request tokens and durations were granted but remained unread | Supply compact request facts by an explicit question, rather than expecting directory exploration |
| Required checks passed before unnecessary continuation in concrete traces | Organize sequences of requirements, actions, results and continuation, not only duration tables |
| Three normal-completion failures have concrete artifact failures despite abnormal final answers | Model self-description is an observation, not an authoritative diagnosis |
| A proposal child saved a validated 23,532-character block before cancellation, but the parent received no useful final handoff | Publish discoverable partial blocks independently of final child completion |
| The selector admitted all 89 cases and 1,602 detailed material paths | Make grouping own case membership; make selection own material supply inside that membership |
| Eval reports Qwen; research Sessions report DeepSeek | Bind actual roles, models and conditions; do not infer same-model RSI from an experiment label |

These observations motivate mechanisms and regression fixtures. They do not establish recovery rates, grouping effectiveness or causal effects. Private verifier information used in the human audit must not silently enter research packets.

## 3. Establish the independent data flow

```text
eval / import -> immutable pool ResearchBatch
                         |
                   explicit group invocation
                         |
                 group-scoped ResearchBatch B
                         |
             group-local evidence selection plan
                         |
                    explicit organize
                         |
              group reading guide + evidence packet
                         |
          explicit propose(parent H, native or GEPA editor)
                         |
              zero or one shared frozen candidate
                         |
                explicit execute on probe tasks
                         |
            explicit compare(measured or model assessor)
```

Each arrow between stages requires a separately selected invocation. A stage may perform its own algorithmic work, but must not invoke the next research stage. In particular, grouping does not start Organizer, and proposing does not execute or select its candidate.

### Keep the three batch counts distinct

| Symbol | Meaning | Owner |
|---|---|---|
| `b` | Distinct source tasks whose feedback enters one proposal | Grouping |
| `K` | Proposal attempts/candidates from a common parent | Explicit researcher invocation plan |
| `V` | Tasks used to evaluate a candidate | Execution/protocol |

Retain actual counts alongside requested counts. Multiple attempts for one task do not create additional distinct tasks. Splitting a long trajectory into reading units does not create extra tasks. Generating K candidates does not mean each one sees K batches. A large-batch group must not silently shrink when its packet exceeds a model window.

### Separate membership from material supply

Grouping fixes a set of task identities and their exact retained executions. Material selection then works only inside that set. It may choose extensions, spans, body depth and supply order. It must not substitute a different task or remove a member to satisfy a character budget.

If some member has no supplied behavioral evidence, record that gap. For the controlled grouping study, do not start the proposal until the declared minimum coverage contract is met; return a structured evidence/space failure rather than a candidate attributed to the requested b. General investigations can retain partial findings, but must not claim the requested group was fully represented.

## 4. Add a standalone grouping owner

### Inputs and outputs

`GroupingRequest` should bind the pool batch identity, exact parent binding where available, requested position, immutable feature artifact, method configuration, and any explicit prior coverage receipts. It must not receive future candidate outcomes, hidden acceptance data or final test results.

`GroupingDecision` should retain:

- source pool and source implementation identities;
- grouping method, parameter identity, seed and invocation position;
- ordered distinct task members and exact run IDs per member;
- feature identity, coverage state before/after and any incomplete-group condition;
- parent-H binding and its assurance, rather than reconstructing historical state;
- a narrow output `ResearchBatch` containing only those tasks, records and observations.

The first public `group` invocation produces **one chosen feedback batch** plus its decision receipt. Repeating the independent stage at explicit positions produces different batches without adding an automatic K-candidate runner. A later multi-group convenience export is unnecessary for the first implementation.

Reuse `ResearchBatch`; do not invent another execution-record format. Reference immutable source artifacts rather than duplicating large trajectories. Publish the narrow batch through the same named bundle/alias mechanism already used by import/execute. Existing organize/propose can consume that published batch using `inputs.batches`.

### Do not leak grouping explanations downstream

Keep two projections:

| Projection | Contents | Consumers |
|---|---|---|
| Full grouping receipt | Algorithm identity, distances, clusters, rationales, seed, coverage and source pool | Research records and offline analysis |
| Safe group binding | Selected task/run identities, opaque scope identity, applicable parent binding and material availability | Organizer and Proposer |

Do not include cluster names, similarity explanations, outside-group observations, global issue guides or grouping-method hints in model prompts. Rebuild batch statistics from B, not from the whole pool. A transitive archive dependency is not a read grant.

Organizer and Proposer may know group membership through their actual examples. The experiment isolates selection composition, not the fact that examples have identities.

### Methods and shared features

| Method | Initial behavior | Delivery order |
|---|---|---|
| `fixed` | Explicit valid task/run members, used for fixtures and exact reproduction | First |
| `random` | Seeded grouping over the eligible pool; deterministic reproduction | First |
| `failure` | Predeclared source-outcome/error classes with explicit success treatment | Next |
| `text` | Task-description relation using a declared provider or frozen representation | Next |
| `trajectory` | Sparse action/observation signatures, weighted similarity and coverage | Next |
| `matched` / `diverse` | Simple-statistic matching or diverse selection on the same declared features | Research extension before stage B claims |

Do not initially train an encoder or ask an LLM to solve all failures before grouping. Deterministic features can include tool classes, observed errors, command repetitions and action transitions. Retain feature availability and unknowns. Normalize instance IDs and temporary-path shortcuts without deleting the behavior under study. Interpretative labels such as “unnecessary testing” require sourced model/human judgments and must not masquerade as deterministic truth.

The feature service belongs to grouping and consumes public evidence references. It may inspect technical representations before grouping without becoming a model Organizer. If LLM extraction is later introduced, freeze it, share its outputs across arms and account for its calls. No method receives richer diagnostic content only because it is the proposed method.

Coverage is explicit state keyed by pool, parent, method and feature identity. No ambient process-global counters. Cache reuse requires unchanged dependencies. A new H cannot silently reuse H0 features as current-H behavior.

## 5. Make trajectory previews reversible

### Three representations remain distinct

| Representation | Retain | Do not claim |
|---|---|---|
| Native Session | Canonical committed messages and available context/operation records | Exact API replay, unavailable internal reasoning, all unfinished deltas |
| ATIF export | Interchange message/action/result view, available returned reasoning and images | Full native metadata or every exact request context |
| Research outline | Every permitted recorded interaction step with typed fields and body references | Complete body supply from message counts or previews |

Keep native originals unchanged. Replace the one-way research excerpt boundary with a permitted-content outline plus immutable full-content resources. The default import need not grant the entire native Session, opaque continuation data or private metadata just to expose a long Bash result.

### A normalized interaction reference

Extend existing evidence contracts to describe:

```text
run_id, event_id, sequence, role, request_id when recorded
tool_call_id, tool_name, command_handle when recorded
content blocks: kind, preview, original_length, content artifact/span
source artifact + original character range
completion state: completed / interrupted / unknown
availability: retained / external / ungranted / unavailable
```

Structured tool parameters remain structured. Long `write.content` or shell scripts become exact body references instead of prefixes presented as if they were valid complete JSON. Preserve observed tool truncation separately from later research preview truncation.

Use an event-oriented reader operation, such as `read_event(event_id, field, offset, limit)`, over existing evidence access. The host resolves artifacts and ranges, enforces group/material grants, and returns the existing exact citations. Models should not calculate raw file offsets or invent source paths. Merely knowing an event ID must not grant its unapproved thinking/image/context extension.

### Default evidence and justified extensions

| Level | Evidence | Reason for admission |
|---|---|---|
| Required | Complete task/output contract, ordered action/observation outline, final response state, termination and source-declared outcome | Establish goal, behavior and result for every group member |
| Required compact facts | Delivery/capture availability and provenance status | Avoid confusing observed writes, captured bytes and readable bytes |
| Targeted extension | Per-request usage/duration | Diagnose generation cost, repetition and timeout |
| Targeted extension | Artifact function/version | Investigate an incorrect deliverable |
| Targeted extension | Explicitly admitted development feedback | Distinguish self-checks from actual acceptance |
| Targeted extension | Compaction/context record | Investigate instruction loss or abrupt task switch |
| Targeted extension | Returned reasoning | Distinguish hypotheses not resolved by actions/usage; not causal proof |
| Targeted extension | Operation intervals/environment facts | Resolve background work, cancellation and infrastructure errors |
| Debug extension | Exact client request snapshot, if actually retained | Investigate Provider projection; server behavior remains unproven |

Record the question, requested category, supplied ranges and cost of each extension. First implement a small explicit request vocabulary, not an autonomous investigative planner. Requests do not silently expand grants; unadmitted materials require a separate explicit import/supplement and another invocation.

### Correct completeness reporting

Keep separate facts for `captured`, `imported`, `granted`, `supplied`, and source parsing/indexing. None proves comprehension. A file captured in Eval but external to the research bundle is `captured + external`, not “never retained.” Final-answer length is not deliverable size. Missing terminal counters are unknown, not zero; observed partial events may support separate lower-bound diagnostics, never invented terminal totals.

New imports freeze exact permitted interaction bodies needed for readback, within declared retention bounds. If a source exceeds retention policy, mark it external/unavailable explicitly. Existing immutable imports remain immutable; reimport or supplement to obtain newly available resources. Do not add configuration versions or fallback configuration grammars.

## 6. Narrow evidence selection to group-local material policy

Keep `improvement-evidence-selection` as an I component, but change its public semantics deliberately. It takes the fixed group and immutable resource/event catalogs, returns per-member materials, spans and admission reasons, and reports supply limits. It cannot change membership.

This requires a reviewed contract change: current `max_cases`, `controls`, `max_per_task`, case-ranking thresholds and `sampling_policy` select executions. Move the needed case-composition policies to grouping. Remove their current configuration positions from material selection; update project callers, fixtures, examples and guides together. Reject obsolete authored fields with a precise error. Historical selection receipts remain readable as historical records with their original meaning, not reinterpreted as a new material plan.

The material owner retains focused/full-granted policies, required categories, optional-category grants and member coverage. Global hard supply ceilings remain with the existing evidence owner. Do not create competing byte counters. A selection plan is not a supply receipt.

Include small capture/source-status diagnostics in focused materials. Keep large manifests behind compact indexes. Proposer inherits the organizer's group scope and the same admitted materials; it does not rerun an independent case selector. A further material decision can narrow bodies, not substitute tasks or invalidate already supplied citations.

## 7. Make Organizer bounded and useful to both editors

Evolve the existing layered method into a code-scheduled extraction path. Preserve its public `OrganizationRequest -> EvidenceView` boundary and strict final submission. Do not demand that Flash plan a large investigation, invent partitions, compute denominators and maintain citation syntax simultaneously.

### Local extraction

The method creates bounded units at request/action/result boundaries, with continuity for long tasks. Each unit asks a small question:

```text
What was required?
What action was taken?
What was actually observed?
What did the Agent do next?
Which requirement or outcome remains unresolved?
```

The model returns event IDs and short observations. Code verifies scope and attaches exact sources. Counts and denominators come from code. This does not establish semantic entailment automatically; exact-quote support and review fixtures remain necessary.

Every member enters the extraction queue. Units are processing partitions, not task-specific candidate optimizations. The simplest implementation is serial with saved progress. Optional existing evidence delegation can execute the same bounded units later; multi-agent collaboration is not required for the research method.

### Group synthesis

Synthesize only inside B. Preserve recurring observations, success contrasts, infrastructure issues, exceptions and open questions. Do not infer population causality from a convenience sample or disprove a harmful effect merely because a successful case contains the behavior. Timing intervals may overlap.

Retain per-task cards and their sources independently of the short top-level guide. Existing root finding limits must not silently erase completed task work. If the synthesis budget surfaces only a subset of observations, publish the remaining-card index and explicit synthesis coverage; never certify that all possible issues were discovered.

Use the current sourced fact/hypothesis/unknown structure. A fact can be established while prevalence and intervention benefit remain unknown. `needs_evidence` on a broad issue must not erase the narrower supported observation.

### Generic reflection packet

Organizer should expose a backend-neutral packet, not a GEPA dependency:

```text
group binding + parent applicability + task/run membership
per task:
  complete input/output contract or exact retrievable reference
  compact chronological observed behavior
  terminal/outcome facts with known/unknown semantics
  admitted feedback, explicitly separate from model interpretation
  selected exact evidence spans and provenance
group observations, contrasting cases and unresolved questions
coverage and truncation/readback status
```

A deterministic packet builder resolves the declared spans through the ordinary reader. Required content cannot disappear through silent string slicing. A tool-free GEPA prompt must fit after final rendering, including template overhead and output reserve. If it cannot fit, return a precise packet-space/evidence result or explicitly rerun organization with another declared budget. Never secretly reduce b or send an oversized request.

The native editor can optionally use this same packet plus scoped read tools. Existing native proposals using their current batch/evidence inputs remain valid without a reflection packet or an Organizer invocation. A packet is a preparation requirement of the selected GEPA method, not a new universal proposal gate. For a controlled native-versus-GEPA experiment, supply the same frozen packet and declare any additional retrieval allowance; that experimental condition does not change native defaults or capabilities.

## 8. Retain partial research work independently of completion

The current evidence delegation saves a block blob and internal block list in `save_findings`, but publishes parent-readable block paths through accepted final submission/finalization. The TB2.1 proposal child demonstrates why those lifecycle points cannot be identical.

Publish a durable, group-scoped partial-block index when a block passes validation. Include child identity, question, exact grants, source spans, artifact identity and state. Make it readable while running and after cancellation/failure. A generic status response should expose a small partial-result reference and count rather than the full block.

Keep `partial`, `submitted`, `cancelled` and `failed` separate. A saved block is useful evidence, not a successful completed investigation. Parent integration must check partial results before declaring no output. A resumed role revalidates grants and identities; it does not replay paid work or inherit direct original-read receipts from a derived block.

Implement these changes in the existing evidence delegation/parts and work-product lifecycle owners. Do not create a second agent service or solve the problem with another prompt alone.

## 9. Use the GEPA Python package for a single proposal

### Preserve the existing proposal and editor methods

```text
existing propose stage and zero/one-candidate contract
  -> selected native method: existing AgentGenerator + workspace AgentEditor
  -> selected GEPA method: reflective instruction adapter + shared validators
```

These are parallel alternatives for one invocation, not successive steps. A GEPA proposal is not passed to the native editor for an unrecorded rewrite. Its metadata-only completion cannot change the proposed text. A missing GEPA dependency or failed GEPA call reports that selected method's admission/runtime failure; it does not silently fall back to the native method. An explicit later native invocation remains available.

The existing stage-level `propose` operation is generic; the workspace editor is one existing concrete method. Keep those two levels distinct. This design chooses the editor-method extension seam, reusing the existing generator, rather than registering the same GEPA behavior simultaneously as both a generator and an editor method.

### Incorporate the local GEPA research collection

The user's existing source card is `/Users/tfifthefrank/harness/wiki/sources/gepa.md`; its preserved paper and code live under `/Users/tfifthefrank/harness/raw/optimization/gepa/bundle/`. The card's paper-v2 interpretation and its later code snapshot are different evidence. The local package metadata declares `0.1.4`, but that declaration alone does not establish equality with the published wheel or an unchanged repository commit.

Source checks relevant to this adapter:

| Local source | Checked content and consequence |
|---|---|
| `src/gepa/core/adapter.py` | `Candidate = dict[str, str]`, `ProposalFn`, `GEPAAdapter.make_reflective_dataset` and optional proposal logic separate representation, reflective data and execution. Coupled component updates are expressible through adapters. |
| `src/gepa/adapters/dspy_full_program_adapter/full_program_adapter.py` | `build_program` compiles/loads candidate program text; `propose_new_texts` uses a program proposal signature. Strings are not intrinsically limited to natural-language instructions. This DSPy execution adapter is not imported or executed by the FruitFlyAgent proposal-only method. |
| `src/gepa/strategies/instruction_proposal.py` | The concrete instruction renderer/extractor is the chosen narrow integration surface; it does not require adopting GEPA's entire optimization engine. |

Verified local content SHA256: adapter `c32c4c2ea8ed9fc4f2c65e8d28184e3f63e10e39546a865e556d351f547d88b5`; full-program adapter `bd1814878a145ede88583400e4a6532473489d58fd5035abee969b8ba010e8d8`; instruction proposal `c3848586365c546afdbfb7ffd6f80b6f49def7575821ff352a29bbcf624bd977`. The first two match the source card's recorded hashes. No source code, repository commands or models were run from that collection, and its files were not modified.

The first-phase single-instruction constraint below is a FruitFlyAgent integration choice, not a general GEPA limitation. Keep the local paper review, local code inspection and published-wheel probe separately attributed; none establishes an end-to-end reproduction or quality gain.

### Verified upstream facts

Checked on 2026-11-19 against PyPI and the actual published wheel:

| Item | Finding |
|---|---|
| Package | `gepa==0.1.4` |
| Python requirement | `>=3.10,<3.15`; FruitFlyAgent currently requires Python >=3.11 |
| License | MIT |
| Base runtime requirements | No unconditional dependencies in the inspected wheel metadata; optional extras add integrations |
| Wheel SHA256 | `12b971039599625c156d2231f6d72a29c31a22e9c237689459b5f1a3c353f532` |
| Useful low-level class | `gepa.strategies.instruction_proposal.InstructionProposalSignature` |
| Input | `current_instruction_doc`, `dataset_with_feedback`, optional `prompt_template` |
| Output | `new_instruction` |
| Available methods | `prompt_renderer`, `output_extractor`, synchronous inherited `run` / `run_with_metadata` |

The package's primary advertised APIs, `optimize` and `optimize_anything`, are optimization drivers. Do not call either for this phase, even with a tiny budget or a fake evaluator: that would transfer execution/selection control to a hidden optimization loop.

The named instruction signature is a lower-level importable implementation surface, not a promised stable top-level one-shot API. Isolate it in one compatibility adapter, pin the version and fail admission if its inspected behavior changes. Do not monkeypatch upstream globals, reconstruct GEPA state, copy upstream source into shared modules, or hide a version fallback reader.

### Offline probe already performed

The published wheel was downloaded into `/private/tmp/fruitfly-rsi-design/gepa-research/`, hash-checked and extracted without installation. An isolated Python 3.13.13 process with `-I -S`, socket connections disabled and only that extracted wheel added to the import path successfully:

1. imported the instruction signature without optional dependencies;
2. rendered two task/feedback examples;
3. called a fake synchronous LM exactly once and parsed one new instruction;
4. confirmed that empty text parses as an empty instruction, requiring host validation.

No real model, task, optimizer or network call ran inside the probe. This verifies the chosen wheel seam, not compatibility across all project-supported Python versions or real Flash proposal quality. Probe files and result are external audit artifacts, not project runtime code.

### Production adapter flow

Keep the existing generator and zero/one-candidate contract. Add a GEPA editor implementation selected through the editor owner:

```text
ResearchProposalRequest
 -> validate one authorized text target and exact parent
 -> validate/assemble frozen group reflection packet
 -> convert packet into GEPA dataset records
 -> GEPA prompt_renderer(explicit owner template)
 -> existing asynchronous prepared editor model runtime
 -> GEPA output_extractor(raw response)
 -> validate proposed text and retain an unsubmitted draft
 -> bounded attribution/decision completion on the fixed draft
 -> existing submission + component validation + candidate export
```

Use renderer/extractor directly around the existing asynchronous runtime. Do not block an event loop with synchronous `Signature.run`, send calls through LiteLLM/DSPy, or construct a new client with independent credentials. Preserve `models.roles.editor`, request accounting, cancellation, persistent role Session, context measurement and output reserve. The prepared role must admit tool-free invocation; current role assembly unconditionally requiring tools is an affected capability boundary.

### Organizer-to-GEPA conversion

The compatibility layer maps generic records to `Inputs`, `Generated Outputs` and `Feedback`. Generated Outputs should contain the relevant action/observation sequence and actual final response state, not only the last answer. Feedback keeps source-declared acceptance, raw measurement, interruption, organizer observations and hypotheses distinguishable. Missing feedback stays unknown; do not invent an evaluator critique or infer a score from prose.

The converter does not regroup, fetch outside B, append pool-level diagnoses or import hidden verifier content. It retains successful examples and source IDs. The final rendered request is frozen so actual supplied examples and exact evidence spans can be audited.

### Limit the first editable surface

For the new GEPA method only, initially support one explicitly granted scalar instruction string, preferably `base_prompt.parameters.instructions.system`. Derive it from owner-admitted grants and field declarations, not a parallel target registry. Reject multiple/ambiguous targets or numeric/library edits when admitting that method, before model construction. These restrictions must not be added to the common `ResearchProposalRequest`, stage-wide grant parser, native editor, or shared candidate validator. The changed instruction still exports as a complete shared Harness preserving all unrelated components.

This restriction makes the first GEPA integration reviewable and faithful to the selected instruction-mutation path. Expanding this method to other text targets or coordinated multi-component edits is a separate implementation and experiment, not a silent capability claim. Native owner-admitted multi-component/parameter editing continues to operate independently.

### Prompt and attribution policy

Upstream's default template encourages retaining instance/domain factual details. The FruitFlyAgent study requires shared operational improvements and excludes task IDs, answers and source-specific exceptions. Use an explicit owner template to state those constraints and preserve the output contract. Record the exact template and call the method **GEPA reflective-proposal adaptation**, not full/original GEPA.

GEPA returns text, while FruitFlyAgent also requires edit reasons, issue attribution, expected effect and an explicit decision. Do not fabricate semantic reasons by attaching every supplied run to the change. Use a second bounded metadata-only completion with the frozen proposed text and same packet; it may cite supplied events/issues or return unsupported/needs-evidence, but cannot modify the proposed text. Validate through the same public submission path. Count this extra call and any repair cost. The exact first-phase budget is one proposal completion plus one metadata completion, with only explicitly bounded schema repair; failures retain drafts and do not silently restart generation.

Empty output is invalid. Identical valid text can yield retain-baseline with a precise unchanged-result reason. Invalid component edits, incomplete packets and runtime failures remain distinct; none implies that the baseline is optimal. Parsed output is not automatically a usable prompt, and syntactic guards cannot prove absence of task-specific memorization.

### Dependency and release handling

Propose an optional `gepa` extra containing `gepa==0.1.4`, without `[full]` or DSPy. Keep ordinary installations and workspace-editor operation usable without it. Only the selected method's admission imports the compatibility dependency. Update third-party notices and frozen dependency/resource receipts. No wheel, unpacked upstream package or research cache belongs in the source distribution.

## 10. Add deterministic comparison beside the model method

Keep compare as the common explicit stage. Add a generic comparator port with two implementations under the existing assessment owner:

| Method | Required input | Behavior |
|---|---|---|
| `measured` | Frozen batches, exact task/attempt pairing, declared objective and outcome policy | Deterministic metrics and comparison; no Provider construction |
| `model` | Same explicit batches plus granted behavioral evidence | Existing assessor judgments and explanations |

Use one common result envelope for input identities, method/policy identity, coverage, resource usage, assurance and conclusion. Method payloads differ: measured results contain per-task facts/deltas; model results contain sourced judgments. Do not synthesize model opinions from numeric scores or rewrite official scores using model choices.

The measured method must:

1. validate declared task membership, repeats, source/scorer identity, initial-state and environment comparability independently of candidate H;
2. pair by task and recorded attempt, not list position or completed-only intersection;
3. preserve planned/observed counts, error rates, source-declared success semantics, raw reward and unknowns;
4. use the same explicit outcome policy as the execution source; error reward 1 is not automatically official success, and missing measurement is not automatically scored zero;
5. compute absolute performance, paired differences, wins/losses, retained successes and regression rate with exact known denominators;
6. apply declared direction, minimum gain, regression constraints and tie rules;
7. return insufficient coverage/comparability when prerequisites fail;
8. publish an auditable per-task table and stable machine result without an LLM.

An explicit manifest of expected tasks/attempts is required to detect missing results from both sides. Do not infer the population from the intersection, or imply comparability merely because opaque historical IDs happen to match. Paired deltas across H are intended; comparison must not require candidate Harness identities themselves to be equal.

The first method may use simple deterministic summaries. Cluster bootstrap, transfer-matrix modeling and independent-evolution statistics belong to the research analysis consumer, using the exported paired table. They need not become default runtime comparison complexity. Frozen seeded uncertainty analysis can be added explicitly later.

The current stage definition labels compare as always requiring assessor. Resolve required roles from the chosen comparator's Catalog declaration before Provider construction. In measured mode neither editor nor assessor credentials should be required. Default to the existing model method for ordinary configurations; research examples explicitly select measured comparison. Changing that default later requires an explicit behavior decision.

## 11. Own configuration and Improvement surfaces

Use the one current H/S/I grammar and existing Catalog declarations. Suggested owner components:

| Component | Role and selectable behavior | Meaningful editable surface | Protected fields |
|---|---|---|---|
| `improvement-grouping` | I; fixed/random and later relation methods | Batch size, coverage policy, method-admitted relation weights or quotas | Pool/run grants, actual source bytes, membership validation and parent binding |
| `improvement-evidence-selection` | I; group-local material policy | Category priorities, admitted detail policy and bounded per-member allocation | Group membership, source identities, global safety/grant bounds |
| `improvement-organizer` | I; bounded layered extraction | Local extraction and group-synthesis prompts | Citation construction, identity and coverage validation |
| `improvement-editor` | I; workspace or GEPA reflective proposal | GEPA template, existing applicable instructions and bounded repair content | Method dispatch, actual package identity, target/grant checks and models |
| `improvement-comparison` | I; measured/model comparison | Declared objective priorities and bounded decision thresholds | Score source, raw measurements, test scope and validator implementation |

Keep current editor identity/implementation position and introduce a Catalog-declared owner method setting rather than algorithm branches in Run. Its normalizer resolves method-specific parameters/defaults from the selected method's registered resource. Inactive-method values cannot authorize edits. An omitted method resolves to existing workspace behavior through ordinary defaults; existing native prompt content, parameter values and edit capabilities must not be overwritten by GEPA defaults. The native path must not import or require GEPA. GEPA defaults exist once under its method package; do not duplicate the upstream prompt as another Python constant.

Comparison similarly exposes one owner method selection. The model branch consumes the existing evaluator component; the measured branch has no model role. Method dispatch stays in Lab's owning factory and its shared Catalog declarations. Do not add a second Assessor registry for this feature.

All new/changed selectable surfaces require owner `improvement.py` entry points, exact field grants, validation, immutable trial identity, source-preserving isolated candidate application and proof that an allowed change affects actual execution. Configuration visibility does not grant optimization authority. In the grouping study these I settings remain frozen even though the project can expose them for separate research. No automatic nested I optimizer is added.

Keep `models.roles` as the only model binding location. Research main YAML declares stage inputs, budgets, position, named outputs and field grants; it does not embed GEPA model aliases or algorithm templates. Save ordinary customizations to referenced workspace component files, preserving authored paths and unchanged references. Freeze effective values and declared resources for candidates and exports.

### Illustrative configuration changes

The following is proposed syntax, not currently accepted configuration:

```yaml
# Research main document, independent invocations.
stages:
  group:
    inputs:
      batches: [{artifact: pool-h0}]
    position: 0
    publish_as: feedback-group-000
    attempt: reuse
  organize:
    inputs:
      batches: [{artifact: feedback-group-000}]
    publish_as: feedback-guide-000
  propose:
    inputs:
      harness: {config: frozen-h0.yaml}
      batches: [{artifact: feedback-group-000}]
      evidence: [{artifact: feedback-guide-000}]
    optimization:
      scope: explicit
      include:
        base_prompt:
          fields: [parameters.instructions.system]
    publish_as: candidate-000
next:
  stage: group
```

The `include.<component>.fields` structure reuses the existing owner grant format. The new `group` stage and `position` control are proposed additions, so this whole excerpt is not yet executable. Grouping seed/b and editor/comparison method are configured in their referenced I documents. `position` is an explicit invocation coordinate, not an algorithm prompt. Setting `next.stage` executes one operation only.

The proposed referenced component documents use the existing identity/role/implementation envelope. For example, the editor keeps `id: improvement-editor`, `role: I`, `implementation: improvement-editor`, with `parameters.settings.method: gepa-reflection`; the new comparison component uses `id: improvement-comparison`, `role: I`, `implementation: improvement-comparison`, with `parameters.settings.method: measured`. Grouping uses `id: improvement-grouping`, `role: I`, `implementation: improvement-grouping`, with owner settings `method`, `batch_size` and `seed`. Their exact admitted parameter sets/defaults are defined once by the corresponding Catalog surfaces. Current loaders must reject these not-yet-registered fields rather than silently ignoring them.

## 12. Place files in their owning modules

Paths marked NEW are proposed. Existing paths are integration points, not permission to rewrite unrelated code.

```text
fruitfly_agent/
  improvement/contracts/
    grouping.py                       NEW: requests, membership and receipt contracts
    comparison.py                     NEW: comparator request/result/port
    evidence.py                       EXTEND: event/body and packet references
    organization.py                   EXTEND: generic reflection packet references
    stages.py                         EXTEND: validate independent group inputs

  lab/improvement/
    grouping/                         NEW owner
      __init__.py
      README.md
      configuration.py
      registration.py
      improvement.py
      features.py                     technical feature extraction and identities
      publication.py                  narrow batch and separate receipt projections
      methods/
        fixed/{__init__.py,algorithm.py,defaults.yaml}
        random/{__init__.py,algorithm.py,defaults.yaml}
        failure/{__init__.py,algorithm.py,defaults.yaml}       later
        text/{__init__.py,algorithm.py,defaults.yaml}          later
        trajectory/{__init__.py,algorithm.py,defaults.yaml}    later

    evidence/
      trajectory.py                   NEW: permitted event/body normalization
      packets.py                      NEW: generic packet assembly/supply
      query.py, tools.py              EXTEND: event-based exact readback
      coverage.py                     FIX: capture/import/grant/supply distinctions
      delegation.py, parts.py         FIX: durable partial-block publication
      access.py, provenance.py        EXTEND: explicit inline packet supply
      batch.py, summaries.py          EXTEND: compact group-local entry view

    evidence_selection/
      configuration.py, registration.py, improvement.py
      methods/focused/                NEW replacement for case-ranking method
        __init__.py
        algorithm.py
        defaults.yaml
      methods/representative/         REMOVE after callers/resources move

    organizer/
      methods/layered/
        algorithm.py                  bounded extraction and synthesis entry
        scheduling.py                 NEW: deterministic bounded unit queue
        extraction.py                 NEW: local extraction and event-ID binding
        defaults.yaml                 extraction/synthesis defaults once
      publication.py, workspace.py    group cards, packet and scope publication
      instructions.py, improvement.py, registration.py

    editor/
      methods/gepa_reflection/        NEW selectable editor method
        __init__.py
        algorithm.py                  one proposal + metadata completion
        compat.py                     only upstream GEPA import/API seam
        dataset.py                    generic packet -> GEPA records
        defaults.yaml                 adaptation and metadata prompts/defaults
        README.md
      methods/workspace/              preserve native editor method
      factory.py                      NEW owner method factory, Catalog-driven
      configuration.py, instructions.py, improvement.py
      submission.py, validation.py     share final authorization/attribution checks
      generators.py                   preserve zero/one-candidate generator path

    assessment/
      methods/measured/               NEW deterministic comparator
        __init__.py
        algorithm.py
        defaults.yaml
        README.md
      methods/model/                  model comparison adapter over assessor
      comparison.py                   shared objective helpers, not host dispatch
      registration.py                 NEW comparison Catalog surface/factory
      improvement.py                  NEW comparison owner grant/trial entry
      promotion.py, measured.py       reuse applicable existing pure helpers

    stages/
      group.py                        NEW independent stage handler
      compare.py                      invoke comparator port
      organize.py, propose.py         fixed group scope/material-plan propagation
      registry.py                     register group and conditional role metadata
    api.py                            public factory/port bindings only
    registration.py, system_configuration.py

  run/improvement/
    service.py                        group stage/public binding composition
    roles.py, research_runtime.py      tool-free editor and conditional model roles
    execution_host.py                 injected factories, no algorithm branches
    configuration/document.py         one grammar for group/method controls
    context.py                        named narrow batches and safe group bindings
    configuration/snapshot.py         method/default/package identities
  run/storage/
    research.py, research_bundles.py   existing immutable output/dependency path

  experiments/
    cli.py                            same show/check/step operations
    templates/                        explicit per-module examples; no auto runner

fruitfly_eval/improvement/
  materials.py                        permitted full body resources + previews
  facts.py, history.py                capture/outcome/source adaptation
  README.md                           exact evidence and diagnostic admission
fruitfly_eval/harbor/
  host.py                             investigate child library-path contamination
  # Add a child-environment correction only after a separate reproducing fixture.

examples/experiments/grouped-feedback/  NEW operational recipe and placeholders
tests/lab/
  test_grouping.py                     NEW membership/features/determinism
  test_gepa_editor.py                  NEW compatibility/output/grants
  test_measured_comparison.py          NEW pairing/outcomes/no-Provider behavior
  test_evidence_selection.py           update material-only behavior
  test_organizer.py                    bounded coverage and packet behavior
  test_editor_execution.py             shared submission path
  test_research_grants.py              existing evidence and group-grant owner
tests/eval/test_reading_materials.py    exact readback and archive availability
tests/run/
  test_research_configuration.py       one grammar/defaults/round-trip
  test_research_delegation.py          partial block after cancellation
tests/experiments/
  test_stage_cli.py                    independent group/compare/propose dispatch
  test_research_continuation.py        explicit parent and named outputs
tests/support/                        reuse existing fake Providers and artifacts

pyproject.toml                        optional pinned GEPA extra + resource inclusion
THIRD_PARTY_NOTICES.md                GEPA attribution and license scope
```

Test paths in this tree express behavior ownership. Check existing test names/support before creating files; do not duplicate discovery or move unrelated tests. In particular, current evidence grant coverage already has owners and should be extended where it lives. Every new independent module gets a README/backlink; small method directories can use their owner's guide where appropriate.

The new `editor/methods/gepa_reflection/` sits alongside `editor/methods/workspace/`. Do not move, delete, rename or replace the workspace implementation as part of GEPA integration. Changes to common factories/configuration should select one method while retaining the existing public `AgentEditor` and `AgentGenerator` entry points. Organizer packet conversion belongs to the new GEPA method's `dataset.py`, so future methods can consume the generic packet without inheriting GEPA-specific fields.

## 13. Publish compact artifacts without duplicating the ledger

Use the existing research store, bundles, dependency hashes and source capture. Proposed logical outputs:

| Stage | Model-facing or executable output | Research-only diagnostics |
|---|---|---|
| import/eval | batch, normalized trajectory outline, permitted body refs | source/capture/coverage receipts and full archive locators |
| group | narrow batch, safe binding | full grouping decision, features, seed and coverage |
| organize | guide/index, per-task cards, reflection packet | supply/read coverage, partial blocks, prompt/output records |
| propose | complete candidate or explicit no-candidate decision | rendered GEPA request, raw response, parsed text, metadata response, draft and validation |
| execute | fixed-candidate execution batch | source conditions, actual usage, cleanup/incomplete coverage |
| compare | common result envelope and paired task table | method inputs, policy and optional uncertainty artifacts |

Record method identity, effective parameters, package/version/resource identity, actual model binding, source group, parent, candidate and phase on every applicable output. Availability of a full grouping receipt or Session in a portable bundle must not automatically grant it to a downstream model.

Incrementally derive a phase cost view from existing request and execution receipts rather than copying another cost ledger. Include unsuccessful calls and repairs. Distinguish reported subtotals, estimates and billed amounts; unknown money remains unknown. Record task count, wall time and concurrency separately. Shared extraction costs need explicit accounting in method comparisons.

## 14. Support the research protocol without implementing its runner

| Research stage | What these modules supply | What remains an explicit research operation |
|---|---|---|
| A | Fixed/random source batches, frozen proposals, source IDs, repeated probe execution, measured paired tables | Candidate–probe matrix, source/target disjointness audit, cluster uncertainty, joint/single-source probe design |
| B | Interchangeable grouping methods, shared packet protocol/editor, exact common parent, comparable outputs | Invoke K attempts per arm, fix all other factors, evaluate source-external candidates and analyze all attempts |
| C | Rebind an explicit candidate for later task execution; preserve versioned evidence and state | Multi-round/multi-arm coordinator, independent evolutions, fixed cost stops and final sealed-test schedule |

For A, do not generate all probe modifications exclusively with the proposed similarity method. Preserve unsuccessful/no-change proposals. Include the protocol's additional joint-feedback versus single-source probes; their extra calls are not part of the illustrative 288 executions.

For B, choose one editor implementation across grouping arms. GEPA reflective proposal can be that shared editor. Compare native versus GEPA editing separately on the same frozen groups/packets. Keep all K attempts tied to the same parent H; sequential invocation is acceptable, parent chaining is not. Define whether K counts attempts or legal candidates and charge replenishment explicitly.

For C, source each arm's training evidence from its actual current H. Repeated evaluation of one H is not an independent evolution. The implementation here does not launch C or claim full GEPA as a baseline. Combee remains absent; the existing protocol's Combee comparisons are deferred, not silently treated as fulfilled or removed from future claims.

Do not present the audited TB2.1 batch, already used for diagnosis, as an untouched final test. Dataset choice is external to this design; split identities and source exclusion are still required research facts.

## 15. Implement and admit modules in bounded increments

| Increment | Concrete delivery | Offline acceptance |
|---|---|---|
| P0: evidence correctness | Readback, task completeness, capture/grant states and partial-block visibility | Recover text after character 2,000; retain original bytes; cancelled-child block remains discoverable |
| P1: measured comparison | Comparator port, measured method, conditional roles | Fixed fixtures give stable deltas/coverage and construct no Provider |
| P2: grouping foundation | Fixed/random methods and standalone group stage; material-only selection | Exact reproducible membership; no outside-group reads or hints; b=1 and large b work |
| P3: bounded organization | Per-task queue/cards, local synthesis and generic packet | Every member accounted for; partial work retained; token overflow is explicit, never silent task removal |
| P4: research grouping controls | Failure/text/trajectory/matched/diverse methods and frozen feature receipts | Same evidence and editor across arms; allowed policy edit changes real isolated membership |
| P5: GEPA editor | Optional pinned package adapter and validated shared candidate | One proposed text, counted metadata completion, same submission checks, no execution/search calls |
| P6: human-invoked pilot | Explicit per-module configurations and cost/result export | Researchers separately authorize actual models/tasks and judge A/B readiness |

P0 and P1 are independent small fixes, not prerequisites for building every other module in one change. P2's boundary tests should precede exposing a sophisticated grouping strategy. Start with one text edit surface, fixed/random groups and a small frozen packet; do not wait for a perfect Organizer or learned metric to test legal source-external candidate effects.

An environment fix for inherited `LD_LIBRARY_PATH` is a separate correctness task: reproduce a child system-program failure and a clean-environment recovery, preserve the Agent interpreter's required libraries, then fix the owning process/environment boundary. Do not make that infrastructure change an unrecorded intervention midway through grouping comparisons.

## 16. Verify public behavior and frozen execution

| Behavior | Required regression |
|---|---|
| Trajectory completeness | Long instruction, long call, tail-only error, image/optional reasoning, interrupted step and multibyte source ranges |
| Exact readback | Preview and body share identity; absent/ungranted differs from missing; source hash changes fail |
| Group isolation | Same pool/seed/position reproduces; stale parent/features reject in strict studies; no outside-group search/catalog or global guide leakage |
| Selection boundary | Changing material policy changes supplied content/identity but never task membership |
| Bounded organization | Every member queued; failed unit explicit; repeat evidence not counted as independent support; no-source fact rejected |
| Partial work | Successful save followed by cancellation/failure yields a scoped readable partial block; unread original citations remain unread |
| GEPA compatibility | Published pinned API import/render/parse; dependency absent produces admission error, not fallback; default runtime works without GEPA |
| Native method preservation | Existing configurations select workspace by default; native proposals work without Organizer/packet/GEPA; multi-component edits still pass their original owner grants; each selected invocation calls only its chosen method |
| GEPA authority | Empty/oversized text, unauthorized targets, invented sources, metadata failure, cancellation and stale parent preserve honest states/drafts |
| GEPA execution isolation | No optimizer, evaluator, task backend, LiteLLM client or production write invoked; configured editor Provider records every actual call |
| Measured comparison | Changed task set, dropped failures, missing both-side attempts, reversed metric, ties, unknown values and incomparable conditions |
| Conditional models | Measured compare and deterministic grouping require no model credentials; selected GEPA editor can be tool-free |
| Configuration/Improvement | One grammar, owner defaults once, file-reference round trip, forbidden edits fail, authorized trial changes actual membership/output/decision |
| Frozen resources | New defaults, package binding and necessary evidence bodies hashed/copied; isolated imports/resource loads have no checkout fallback |
| Independent stages | group does not organize; organize does not propose; propose does not execute; compare does not activate |

Use synthetic, legally shareable fixtures distilled from the observed failure shapes, not copies of hidden task answers or private grader source. Fake output verifies contracts, not model quality or transferable gains. Reuse existing artifact/Provider helpers. Contract changes need synchronized callers/docs/tests; do not widen architecture allowances, skip failing behavior or regenerate assertions merely to pass.

For each implementation increment run its relevant offline tests, then the full suite for behavior changes:

```bash
.venv/bin/python -m unittest discover -s tests -t .
```

For main CLI changes also run `.venv/bin/python -m fruitfly_agent --help`; for Eval entry changes run `.venv/bin/python -m fruitfly_eval catalog --json`. New example configurations must pass the public offline parser/validator before any paid demonstration.

## 17. Update documentation with the eventual implementation

Update the owning guides, not just this design:

- `CONFIGURATION.md` remains the navigation root.
- Runtime architecture describes grouping/material/proposal/comparison ownership.
- `lab/catalog/CONFIGURATION.md` describes admission and editable/protected surfaces.
- `experiments/CONFIGURATION.md` describes independent group inputs/position and stage effects.
- Grouping, Evidence, Evidence selection, Organizer, Editor and Assessment own their behavior/limits.
- Eval's improvement guide distinguishes preserved originals, normalized permitted bodies and optional diagnostic admission.
- New examples explain manual invocation, placeholders and model/container cost beside the operations.
- Packaging and third-party notices identify GEPA's pinned dependency and the adapted scope.

Preserve one current authored configuration grammar. Update repository examples rather than shipping fallback readers. Historical persisted records may retain necessary schema checks and attribution. No installed defaults are edited by ordinary user saves. No new `docs/` tree or implicit migration side effect is introduced.

## 18. Resolve implementation risks explicitly

| Risk | Decision or gate |
|---|---|
| Lower-level GEPA API changes | Pin 0.1.4; compatibility tests and admission checks; upgrade only as a recorded dependency change |
| Prompt/packet format biases a grouping arm | Freeze the shared representation/template and record actual supplied content |
| GEPA default encourages factual memorization | Use explicit shared-Harness adaptation; label the method honestly and retain source-specific-content review limits |
| Root guide hides rare observations | Preserve task cards and unsynthesized scope independently of top-level guide limits |
| Useful text does not fit a single GEPA request | Explicit needs-evidence/space outcome or a separately declared packet budget; no hidden multi-proposal aggregation |
| Citation receipt becomes a false reading claim | Record host extraction, derived card supply and original quote supply as distinct events |
| New I surfaces become self-authorizing | Freeze study policies; owner grants/trials remain separate from adoption; no nested I search |
| Environment/model service changes during study | Capture and disclose conditions; do not infer immutable weights from an alias |
| Only legal candidates improve on their sources | Source-external execution in stage A remains the gate; no grouping-quality claim from legal edits alone |

## 19. Sources and verification record

External primary sources:

1. [GEPA PyPI release 0.1.4](https://pypi.org/project/gepa/0.1.4/).
2. [Published release metadata](https://pypi.org/pypi/gepa/0.1.4/json).
3. [Upstream instruction proposal implementation](https://github.com/gepa-ai/gepa/blob/main/src/gepa/strategies/instruction_proposal.py). The downloaded published wheel, not mutable main, was used for the offline probe.
4. [GEPA paper](https://arxiv.org/abs/2507.19457), for distinguishing reflective mutation from the full optimizer.

Local inputs:

- Research protocol: the user-supplied external `trajectory-batch-experiments.md` and its linked main/revision notes.
- Original TB2.1 archive listed in section 2.
- Earlier audit: `/private/tmp/tb21-evidence-review/README.md`, `minimum-evidence.json`, `trajectory-completeness.json` and `evidence-chain.md`.
- GEPA probe: `/private/tmp/fruitfly-rsi-design/gepa-research/probe.py` and `probe-result.json`.
- Existing local GEPA source card: `/Users/tfifthefrank/harness/wiki/sources/gepa.md`; selected raw adapter/proposal files are identified and hashed in section 9. Paper interpretation is a research reference; the package seam is verified against actual source and the separate published-wheel probe.

Validation completed for this design: inspected current owner contracts/source and the published GEPA wheel; verified its SHA256; passed the isolated no-network fake-LM probe. No project implementation, model/task execution, full GEPA run or quality experiment was performed. The project suite is not required for this design-only document; implementation increments have the checks specified above.
