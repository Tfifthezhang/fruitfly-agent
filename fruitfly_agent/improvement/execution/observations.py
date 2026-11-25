"""Project executed receipts into the shared research measurement contract."""
from dataclasses import replace

from fruitfly_agent.improvement.contracts.observations import MeasurementObservation
from fruitfly_agent.improvement.contracts.research import ObservationSemantics
from fruitfly_agent.improvement.contracts.versions import content_hash

MEASUREMENT_PATH = 'research/measurement.json'


def execution_observation(record, measurement, attempt, read, *, policy_id=None):
    resource = next((r for r in record.artifacts if r.path == MEASUREMENT_PATH), None)
    if resource is not None:
        observation = MeasurementObservation.from_dict(read(resource))
        if (observation.run_id, observation.task_id) != (record.run_id, record.task_id):
            raise ValueError('backend measurement differs from its receipt')
        return replace(observation, attempt=attempt).to_dict()
    policy = measurement.policy_id if measurement is not None else policy_id or 'unavailable-measurement'
    facts_resource = next((r for r in record.artifacts if r.path == 'execution-facts.json'), None)
    facts = read(facts_resource) if facts_resource else {}
    return MeasurementObservation(record.run_id, record.task_id, attempt, policy,
        measurement.score if measurement else None,
        measurement is not None and record.status == 'completed', ObservationSemantics(),
        None, content_hash(policy), None,
        '' if measurement else 'No attributed measurement was returned.',
        elapsed_seconds=facts.get('elapsed_seconds'),
        comparison={'material': record.material_id, 'conditions': record.conditions_id,
                    'initial_state': record.initial_state_id, 'source': 'native execution receipt'}).to_dict()
