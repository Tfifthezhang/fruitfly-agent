# Improvement Host

[Up: Run](../README.md)

Resolve one research request, construct only its needed role/backend, and retain
configuration and portable outputs. The host does not run a continuous search.

| File or module | Responsibility |
|---|---|
| [Configuration](configuration/README.md) | Stage-oriented intent and output-only history |
| `context.py` | Branch-scoped named references and selected stage inputs |
| `service.py` | Independent stage bindings over the injected controller |
| `roles.py` | Shared model catalog and requested-role construction |
| `research_runtime.py` | Persistent research roles and assigned-evidence child runtime ownership |
| `configuration/snapshot.py` | Immutable snapshots, differences and complete candidate export |
| `execution_host.py` | Registered backend preparation and one execution batch |
| `candidates.py`, `versions.py`, `startup_versions.py` | Separate candidate review, identity and activation checks |
| `state_updates.py` | Retained-content configuration binding |
| `evolution.py` | Generic capability-injected RSI adapter; no automatic Improvement composition |

Use the [developer guide](../../lab/improvement/DEVELOPER_GUIDE.md) for main-file
syntax, stage ownership, named inputs and output layout. [Lab](../../lab/improvement/README.md)
owns role algorithms; [Storage](../storage/README.md) owns journals and immutable
artifacts. [Adapters](../adapters/README.md) present read-only records and candidate
review separately from execution authority.

Independent invocations save requested/effective configuration, source receipts
and informational differences before model/task calls. Changed settings do not
reject historical evidence. Complete candidate configs retain unchanged values
and resources; following a candidate is an explicit research choice, not adoption.
The selected registered backend owns fresh execution state and retirement.

```bash
.venv/bin/python -m unittest tests.run.test_research_configuration tests.experiments.test_stage_cli tests.experiments.test_research_continuation
```

Research import passes explicit task names and original path/hash selections to
the source adapter. The stage service does not require model organization before
assessment/proposal. Evidence budgets are shared role settings, not Eval branches
in the runtime. See [configuration](../../experiments/CONFIGURATION.md).

Explicit stage delegation constructs an independent research Session and managed
Subagent scope. Lab's public EvidenceDelegation capability owns material grants,
read-only tools and source validation. Run owns Sessions, independent Providers,
context state and retirement. The same stage factory shares allowance counters
across repeated role invocations; child completion never implies parent original
reading. See [operational controls](../../lab/improvement/DEVELOPER_GUIDE.md#delegate-read-only-evidence-investigation).

Batch loading validates immutable manifests without pre-reading all original
attachments. Actual artifact access verifies content hashes. Case/material
selection is an injected Lab policy; the host records its identity and selection
receipt. Multi-batch input rejects conflicting task/run identities and deduplicates
identical observations. See [bounded investigation](../../lab/improvement/evidence_selection/README.md).
