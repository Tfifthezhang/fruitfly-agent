# Select evidence materials

[Up: Improvement](../README.md)

The evidence selector makes a material plan for every execution in a frozen
batch. The batch determines the tasks and attempts. Use [Grouping](../grouping/README.md)
to compose another batch.

The `improvement-evidence-selection` I component exposes these fields under
`parameters.settings`.

| Field | Behavior |
|---|---|
| `material_policy` | `trajectory-only` selects trajectories, body references and indexes. `focused` adds standard execution diagnostics and deliverables. `all-granted` includes every authorized retained resource. |
| `optional_categories` | Add `outputs`, `termination`, `usage` or `capture` independently. Each added path records its admitting category. |

Task requirements and compact execution receipts remain available as stage
context. A material plan records authorization and does not attest to reading
or availability. Propose can reuse the Organizer plan for the same batch.
Former case count, anomaly threshold and sampling settings are rejected by the
current component. Historical selection receipts retain their original meaning.

Developer extensions register a selector through `register_evidence_selector`.
The host validates exact task and execution membership on its output.
Offline checks use `tests.lab.test_evidence_selection` and
`tests.lab.test_research_grouping`.

[Historical representative algorithm](methods/representative/README.md)
