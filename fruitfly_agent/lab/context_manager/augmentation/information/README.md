# Information Spaces

[Up: Augmentation](../README.md)

Retrieve read-only local documents and live HTTP results through shared query and context-budget interfaces. [Memory](../memory/README.md) and [Skills](../skills/README.md) own independent progressive loaders.

## Sources

| Source | Default | Behavior |
|---|---|---|
| [Local knowledge](methods/local_knowledge/README.md) | Disabled; `.fruitfly/knowledge/` | Read-only lexical retrieval with path/line citations |
| [Live HTTP](methods/live_http/README.md) | Disabled; explicit HTTPS endpoint | Query a service for text |

These sources require the hidden H `information-context` policy (`top_k=5`,
`max_chars=4000`). The menu enables dependencies through Catalog declarations.
Explicit files must include required owners. Source switches appear under Context
augmentation; there is no separate retrieval-policy menu. Retrieved content is
untrusted data. Connector/source content is protected, while selection count and
projection size remain optimizable through the shared H policy.

## Use the API

```python
from pathlib import Path
from fruitfly_agent.lab.context_manager.augmentation.information import InformationHub, InformationQuery
from fruitfly_agent.lab.context_manager.augmentation.information.methods.local_knowledge import create_local_knowledge_space

hub = InformationHub()
hub.register(create_local_knowledge_space(Path(".fruitfly/knowledge")))
# In an async function:
# result = await hub.pipeline.search(InformationQuery("How is this project configured?"))
```

| Operation | Result |
|---|---|
| `search` | Hits and retrieval errors; does not itself apply final context budgets |
| `select` | Post-processed hits |
| `recall` | Applied information for augmentation |

The built-in applicator's character limit covers its rendered data notice, citations, separators, and block markers. Original prompt text and independent trusted guidance are outside that limit. Candidate selection budgets do not guarantee a final projection bound; custom applicators must enforce one.

## Extend a source

| Contract | Input / output |
|---|---|
| `InformationRetriever` | `retrieve(query)` → hits |
| `InformationReader` | `get(ref)` → artifact or `None` |
| `InformationPostProcessor` | Query and hits → selected/ranked hits |
| `InformationApplicator` | Query and hits → effect or `None` |
| `InformationQueryBuilder` | Messages → query or `None` |

Interfaces permit sync or async results. Artifacts need stable `InformationRef(space_id, artifact_id)` and checkable provenance. Inject I/O dependencies, declare state/cache and budgets, and register the source with `InformationHub`. To expose configuration, add a [Catalog](../../../catalog/README.md) definition requiring `information-context`.

| File | Responsibility |
|---|---|
| [protocols.py](protocols.py) | Source and pipeline contracts |
| [models.py](models.py) | Queries, artifacts, references, and effects |
| [spaces.py](spaces.py) | Space composition |

No module-specific environment variables. Synchronous scanning, expiry clock injection, source-error reporting, and HTTP cancellation have limits; see [Known limitations](../../../ALGORITHM_AUDIT.md).

```bash
.venv/bin/python -m unittest tests.lab.test_information_sources tests.lab.test_information_pipeline tests.lab.test_information_adapters -v
```

The Catalog installer passes the configured hub query builder into the context
transformer. Authorized `top_k` and `max_chars` candidates therefore affect the
actual retrieval query and rendered context. The owner's parameter adapter uses
shared configuration materialization. Offline regression:
`tests.lab.test_parameter_candidates` compares Provider-visible retrieval results.

[information-context.yaml](information-context.yaml) owns retrieval count and character defaults. Text and numeric candidates use ordinary owner validation and shared configuration materialization.
