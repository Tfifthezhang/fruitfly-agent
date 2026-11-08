"""Expose explicitly supplied feedback resources without summarizing signals."""
from dataclasses import replace


def readable_context(ports, inputs):
    resources = list(inputs.evidence + inputs.assessments + inputs.context)
    # Assessment produces an annotated ResearchBatch. Its attached feedback must
    # be readable even when the original batch remains the primary observation.
    # Comparison reports remain ordinary context documents.
    for index, resource in enumerate(inputs.assessments):
        if resource.path.rsplit('/', 1)[-1] != 'batch.json':
            continue
        batch = ports.read_batch(resource)
        for record in batch.records:
            resources.extend(replace(item, path='feedback/' + str(index) + '/' +
                record.run_id + '/' + item.path) for item in record.artifacts)
    return tuple(resources)
