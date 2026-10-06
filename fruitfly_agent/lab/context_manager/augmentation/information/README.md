# Information Spaces

[Up: Augmentation](../README.md)

Retrieve file notes, local documents, and live HTTP results through shared query and context-budget interfaces. Skills are a separate augmentation capability.

## Sources

| Source | Default | Behavior |
|---|---|---|
| [File memory](file_memory/README.md) | Enabled; `.fruitfly/memory/` | Index and topic notes maintained with ordinary file tools |
| [Local knowledge](local_knowledge/README.md) | Disabled; `.fruitfly/knowledge/` | Read-only lexical retrieval with path/line citations |
| [Live HTTP](live_http/README.md) | Disabled; explicit HTTPS endpoint | Send the current query to a service and retrieve text |

All sources depend on the hidden `information-context` mechanism. Set its `top_k=5` and `max_chars=4000` parameters in YAML. Source switches appear under **Context Manager**. Retrieved content is untrusted data.

## Use the API

```python
from pathlib import Path
from fruitfly_agent.lab.context_manager.augmentation.information import InformationHub, InformationQuery
from fruitfly_agent.lab.context_manager.augmentation.information.local_knowledge import create_local_knowledge_space

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
