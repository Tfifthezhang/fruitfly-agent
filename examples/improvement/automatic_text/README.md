# Offline Automatic Text Search

[Up: Improvement Examples](../README.md)

Run the complete [automatic workflow](../../../fruitfly_agent/lab/improvement/automatic/README.md) without keys, network calls or paid models:

```bash
.venv/bin/python -m examples.improvement.automatic_text.offline
```

Expected output:

```text
Offline confirmed candidate: ready for human review.
Explicit adoption: new session uses the candidate.
Scripted results demonstrate workflow behavior, not model quality.
```

[offline.py](offline.py) creates a temporary schema-2 task pack and model catalog, registers a scripted Provider, and assembles OPRO, model-based failure processing and automatic text search through Run/Application. It generates a learning exercise different from the source task, records separate material review, searches a text candidate, and confirms on an unseen input. The runtime remains unchanged until an explicit host adoption action representing user approval. Temporary artifacts and Sessions are removed after closing owned resources.

The scores and usage are scripted control-flow fixtures, not measurements of learning, cost or model capability. Real configured Providers require network access and may incur charges for the Agent, material generator, reviewer, improver and confirmation trials. This example does not implement a τ-bench or SWE-bench improvement adapter.

```bash
.venv/bin/python -m unittest tests.workflows.test_automatic_improvement -v
```
