"""Broad then focused verified practice with frozen-memory deployment."""
import json

from fruitfly_agent.lab.algorithms import Algorithm, AlgorithmSpec
from fruitfly_agent.lab.improvement.contracts.search import SearchCandidate, SearchResult
from fruitfly_agent.lab.improvement.runtime.services import BudgetExhausted
from .. import MethodUsage
from ..evidence import check_problem, encode, training_evidence, observe_candidate


class MemoryExplorationImprover(Algorithm):
    spec = AlgorithmSpec('memory-exploration', 'verified-memory-exploration-v1', 'session')
    supported_roles = frozenset({'S'})
    supported_schemas = frozenset({'environment-memory-v1'})
    required_capabilities = frozenset({'evaluate', 'complete', 'history'})
    usage = MethodUsage('Explicit /improvement on Environment memory.',
        'An initial memory and authorized, independently scored training/selection tasks.',
        'Actual practice outcomes and verifier feedback, including grounded failures.',
        'Curriculum selects broad practice then focused practice; evidence is consolidated into memory.',
        'Strict selection improvement is required before publishing a frozen memory candidate.',
        'Review and activate memory in a new session; exploration and updates stop at deployment.')

    async def search(self, problem, services):
        check_problem(problem, self.supported_roles, self.supported_schemas)
        params, memory = dict(problem.parameters), problem.baseline.text
        seed, score, accepted, outcomes, reason = None, None, [], [], 'completed'
        try:
            baseline = await services.evaluate(memory, 'validation')
            seed = score = baseline.score
            if score is None:
                return SearchResult((), None, 'baseline_unmeasured')
            for round_index in range(params['rounds']):
                services.check()
                broad = round_index < params['broad_rounds']
                limit = min(params['practice_batch_size'] if broad else 1, len(problem.train))
                try:
                    response = await services.complete('curriculum',
                        'Choose informative authorized practice tasks. Return only a JSON array of distinct integer task indices. '
                        'Broad exploration covers diverse tasks; focused exploration targets gaps and fragile successes.',
                        encode({'phase': 'broad' if broad else 'focused', 'memory': memory,
                            'tasks': [{'index': i, 'input': c.input} for i, c in enumerate(problem.train)],
                            'previous_outcomes': outcomes[-12:], 'max_tasks': limit}))
                    indices = json.loads(response)
                    if (not isinstance(indices, list) or not 1 <= len(indices) <= limit
                            or any(type(i) is not int or not 0 <= i < len(problem.train) for i in indices)
                            or len(set(indices)) != len(indices)):
                        raise ValueError('curriculum must select distinct authorized training indices')
                except BudgetExhausted:
                    raise
                except (ValueError, TypeError) as exc:
                    services.record('curriculum-rejected', reason=str(exc))
                    continue
                cases = tuple(problem.train[i] for i in indices)
                practice = await services.evaluate(memory, 'train', cases=cases)
                evidence = training_evidence(practice, problem.train)
                services.record('memory-practice', phase='broad' if broad else 'focused',
                    case_ids=[c.case_id for c in cases], score=practice.score)
                if practice.score is None or not evidence:
                    continue
                outcomes.extend(evidence)
                try:
                    candidate = await services.complete('improver',
                        'Consolidate verified training experience into a reusable environment memory. '
                        'Return only the complete updated Markdown document. Preserve useful knowledge, '
                        'revise contradictions and record procedures, conditions and failure lessons. '
                        'Distinguish observed facts from hypotheses. Do not memorize task-specific answers.',
                        encode({'memory': memory, 'verified_experience': evidence}))
                    services.validate(candidate)
                except BudgetExhausted:
                    raise
                except (ValueError, TypeError) as exc:
                    services.record('memory-consolidation-rejected', reason=str(exc))
                    continue
                if candidate == memory:
                    continue
                selection = await services.evaluate(candidate, 'validation')
                passed = selection.score is not None and problem.policy.better(selection.score, score)
                retain = selection.score is not None and problem.policy.utility(selection.score) >= problem.policy.utility(score)
                services.record('memory-gate', accepted=passed, retained_for_practice=retain,
                    selection_score=selection.score, previous_score=score)
                if retain:
                    memory = candidate
                if passed:
                    memory, score = candidate, selection.score
                    accepted = [SearchCandidate(memory, score, (('Memory learning', 'Broad then focused verified practice'),))]
                    candidate_training = await services.evaluate(memory, 'train', cases=cases)
                    if await observe_candidate(services, memory, candidate_training, selection):
                        reason = 'ready_for_confirmation'
                        break
        except BudgetExhausted:
            reason = 'budget_exhausted'
        return SearchResult(tuple(accepted), seed, reason)


def definition():
    from .registration import definition as build
    return build()


__all__ = ['MemoryExplorationImprover', 'definition']
