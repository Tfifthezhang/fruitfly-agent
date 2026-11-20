"""Compose one feedback batch without constructing model services."""
from fruitfly_agent.improvement.contracts.activities import ActivityResult

from ..grouping.publication import compose
from ..grouping.features import frozen_features


async def group(ports, spec, inputs):
    if len(inputs.batches) != 1:
        raise ValueError('group requires exactly one pool batch')
    source, = inputs.batches
    pool = ports.read_batch(source)
    table = frozen_features(pool, ports.read)
    feature_receipt = ports.put('features.json', {'source_pool': source.artifact_id,
                                                  'implementation': 'group-features-v1', 'tasks': table})
    batch, decision = compose(pool, source.artifact_id, spec.parameters.get('grouping', {}),
                              spec.parameters.get('position', 0), spec.parameters.get('members'), features=table)
    decision['features'] = feature_receipt.artifact_id
    decision['implementation_source'] = spec.parameters.get('implementation_source')
    selected = ports.put('batch.json', batch.to_dict())
    decision['batch'] = selected.artifact_id
    return ActivityResult((selected, ports.put('grouping.json', decision), feature_receipt))
