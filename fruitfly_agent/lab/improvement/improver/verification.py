"""One fixed final comparison. Private episodes never return to proposal work."""
from dataclasses import asdict

from ..contracts.pipeline import SelectionDecision, canonical_json
from ..contracts.versions import content_hash
from ..contracts.experiments import TrialReport


def combine(reports):
    first = reports[0]
    if any((r.experiment_id, r.instructions_id, r.initial_harness_id, r.partition) !=
           (first.experiment_id, first.instructions_id, first.initial_harness_id, first.partition) for r in reports):
        raise ValueError('cannot combine mismatched trial reports')
    return TrialReport(first.experiment_id, first.instructions_id, first.initial_harness_id, first.partition,
        tuple(v for r in reports for v in r.gains), tuple(v for r in reports for v in r.regressions),
        sum(r.failures for r in reports), sum(r.model_calls for r in reports), sum(r.executions for r in reports),
        tuple(v for r in reports for v in r.episode_ids), tuple(v for r in reports for v in r.evidence),
        case_gains=tuple(v for r in reports for v in r.case_gains))


class ImproverVerification:
    policy_id = 'improver-paired-v1'

    def __init__(self, runner, claim):
        self.runner, self.claim = runner, claim
        self.receipt = None
        self.consumed = False

    async def verify(self, outcome):
        if self.consumed:
            raise ValueError('independent verification is one-use; never replay unknown work')
        self.consumed = True
        runner, params = self.runner, self.runner.parameters
        baseline = runner.context.components.snapshot()
        if outcome.harness == baseline:
            return None
        self.claim(runner.materials.verification_key, runner.materials.max_verifications)
        reports: dict[str, list[TrialReport]] = {'before': [], 'after': []}
        for repeat in range(params['repetitions']):
            order = (('before', baseline), ('after', outcome.harness))
            for name, harness in order if repeat % 2 == 0 else reversed(order):
                reports[name].append(await runner.trial(harness, 'verification', repeats=(repeat,)))
        before, after = combine(reports['before']), combine(reports['after'])
        expected = params['repetitions'] * len(runner.materials.verification)
        if (before.failures or after.failures or len(before.gains) != expected or len(after.gains) != expected
                or before.experiment_id != after.experiment_id or before.initial_harness_id != after.initial_harness_id):
            return None
        paired = tuple(b - a for a, b in zip(before.gains, after.gains))
        case_pairs = tuple(y - x for a, b in zip(before.case_gains, after.case_gains) for x, y in zip(a, b))
        if (any(v < -params['max_regression'] for v in after.regressions) or
                not case_pairs or any(v < -params['max_regression'] for v in case_pairs) or
                any(v < -params['max_regression'] for v in paired) or
                sum(paired) / len(paired) <= params['min_gain'] or
                after.model_calls > max(1, before.model_calls) * params['max_model_ratio']):
            return None
        payload = {'schema_version': 1, 'policy_id': self.policy_id,
            'source_id': runner.materials.source_id, 'experiment_id': runner.spec.conditions_id,
            'conditions_id': outcome.plan.conditions_id, 'parent': asdict(outcome.plan.parent),
            'harness_id': outcome.harness.snapshot_id, 'run_id': outcome.selected.run_id,
            'parameters': params, 'before': asdict(before), 'after': asdict(after)}
        self.receipt = runner.context.artifacts.put(canonical_json(payload).encode())
        runner.context.services.record('independent-verification', receipt=self.receipt,
                                       policy_id=self.policy_id, experiment_id=runner.spec.conditions_id)
        return SelectionDecision(outcome.selected.run_id,
            'Passed paired independent improver trials; evidence: ' + self.receipt, 'verified')
