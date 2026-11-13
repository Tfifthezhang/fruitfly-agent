# Select Investigation Evidence

[Up: Improvement](../README.md)

The evidence selector is an I policy. It chooses bounded detailed cases from all
compact execution summaries. It cannot edit candidates, execute tasks, assign
task quality or activate a component. Hosts inject the public
`EvidenceSelector` contract; selection is independent of organizer/editor models.

| Entry | Responsibility |
|---|---|
| `configuration.py`, `registration.py` | Strict settings, installed defaults and Catalog surface |
| `improvement.py` | Field grants and isolated candidate selector construction |
| [Representative method](methods/representative/README.md) | Default deterministic selection |

`improvement-evidence-selection` belongs in system I components. Ordinary saves
retain default/file references. Frozen candidates include complete settings and
the packaged default resource. Editable paths are `parameters.settings.max_cases`,
`controls`, `max_per_task`, `slow_seconds`, `many_calls`, `many_tools` and `high_tokens` under the same prefix. `parameters.settings.material_policy` chooses `focused`
or `all-granted`. Focused grants retain trajectories, deliverables and relevant
execution facts/diagnostics; capture directories remain archived. The full policy
only grants already retained resources, never unsupplied external originals.
Identity, role, schema, evidence grants and receipt identities are protected.
Numeric grants may narrow owner bounds. Selection is stateless; each call starts
from the supplied summaries. Changes require an independent research comparison
before persistent activation; normal task comparison cannot verify this I policy.

`candidate_selector` validates an authorized detached document and constructs the
actual trial policy. Different settings change selected cases and identity while
retaining source documents. There is no automatic nested trial or adoption.
Offline checks: `tests.lab.test_evidence_selection`.

Organize/propose retain all summaries and give detail tools only selected task and
execution paths. Selection reasons, distribution counts and omitted scope remain
readable. Full archived materials are preserved; a later investigation must
explicitly select additional cases. A selection receipt is not an original read.

Embedding hosts set `StageBindings.evidence_selector`; developer extensions bind
the same port through `register_evidence_selector(factory)`. The factory receives
Catalog component settings and returns a fresh policy. Its `select` consumes
summary rows plus immutable resource manifests and returns selected run IDs and
optional exact `material_paths`. Out-of-grant material paths fail before access.
