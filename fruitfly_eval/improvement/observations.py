"""One official-outcome projection for retained and live benchmark executions."""
from fruitfly_agent.improvement.contracts.observations import MeasurementObservation
from fruitfly_agent.improvement.contracts.research import ObservationSemantics
from fruitfly_agent.improvement.contracts.versions import content_hash
from fruitfly_eval.results import public_trial_outcome

OUTCOME_POLICY = content_hash('FruitFlyAgent Eval trial_outcome: errors unknown; passed met; failed unmet')


def official_observation(record, trial, *, source_identity, attempt=0, native=False, context=None):
    public = public_trial_outcome(trial)
    eligible = public['eligible'] and record.status == 'completed'
    outcome = {'passed': 'met', 'failed': 'unmet'}.get(public['status'], 'unknown') if eligible else 'unknown'
    if context is not None:
        from .measurement_context import validate
        validate(context)
    return MeasurementObservation(record.run_id, record.task_id, attempt, 'official_reward',
        public['reward'], eligible, ObservationSemantics(outcome, 'higher'),
        context['scorer_id'] if context is not None else None, OUTCOME_POLICY, source_identity,
        '' if eligible else 'Official outcome unavailable or execution interrupted.',
        raw_value=(trial.get('verifier_result') or {}).get('rewards'), error=public['error'],
        official_status=public['status'],
        elapsed_seconds=public['agent_elapsed_seconds'],
        cost_usd=(trial.get('agent_result') or {}).get('cost_usd'),
        comparison=context['comparison'] if context is not None else ({'material': record.material_id, 'conditions': record.conditions_id,
                     'initial_state': record.initial_state_id, 'source': 'native frozen execution'} if native else
                    {'source': 'Retained evidence does not reconstruct initial state or execution conditions.'})).to_dict()
