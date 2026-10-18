"""Bounded feedback-driven optimization of a reusable Skill document."""
import json

from fruitfly_agent.lab.algorithms import Algorithm, AlgorithmSpec
from fruitfly_agent.lab.improvement.contracts.search import SearchCandidate, SearchResult
from fruitfly_agent.lab.improvement.runtime.services import BudgetExhausted
from .. import MethodUsage
from ..evidence import check_problem, encode, training_evidence, observe_candidate


def apply_edits(text, edits, limit):
    if not isinstance(edits, list) or not 1 <= len(edits) <= limit:
        raise ValueError('edit list exceeds the declared edit budget')
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {'op', 'old', 'new'}:
            raise ValueError('each edit requires exactly op, old and new')
        op, old, new = edit['op'], edit['old'], edit['new']
        if not all(isinstance(v, str) for v in (op, old, new)):
            raise ValueError('edit fields must be strings')
        if op == 'add' and not old and new.strip():
            text = text.rstrip() + '\n\n' + new
        elif op in {'replace', 'delete'} and old and text.count(old) == 1:
            if (op == 'delete' and new) or (op == 'replace' and not new.strip()):
                raise ValueError('invalid replacement or deletion')
            text = text.replace(old, new, 1)
        else:
            raise ValueError('edit requires an unambiguous target and a supported operation')
    return text


EDIT_SYSTEM = ('Optimize reusable procedural knowledge from measured TRAINING evidence. '
    'Do not copy task-specific answers into the skill. Return only a JSON array of edits: '
    '{"op":"add|replace|delete","old":"exact unique text, empty for add","new":"text, empty for delete"}.')


class SkillEditImprover(Algorithm):
    spec = AlgorithmSpec('skill-edit', 'bounded-skill-edit-v1', 'session')
    supported_roles = frozenset({'S'})
    supported_schemas = frozenset({'skill-document-v1'})
    required_capabilities = frozenset({'evaluate', 'complete', 'history'})
    usage = MethodUsage('Explicit /improvement on Skill document.',
        'Disjoint scored training and selection tasks, and an initial Skill body.',
        'Successful and failed training executions; errors are not learning evidence.',
        'Minibatch reflection, merged bounded add/delete/replace edits and rejected-edit memory.',
        'Strict improvement on selection tasks; ties and regressions are rejected.',
        'Review and activate the frozen Skill document in a new session.')

    async def search(self, problem, services):
        check_problem(problem, self.supported_roles, self.supported_schemas)
        params = dict(problem.parameters)
        current, seed, score, rejected, accepted = problem.baseline.text, None, None, [], []
        reason = 'completed'
        try:
            baseline = await services.evaluate(current, 'validation')
            seed = score = baseline.score
            if score is None:
                return SearchResult((), None, 'baseline_unmeasured')
            for round_index in range(params['rounds']):
                services.check()
                # Rotate bounded batches without changing the frozen training split.
                size = min(params['rollout_batch_size'], len(problem.train))
                cases = tuple(problem.train[(round_index * size + i) % len(problem.train)] for i in range(size))
                training = await services.evaluate(current, 'train', cases=cases)
                evidence = training_evidence(training, problem.train)
                if training.score is None or not evidence:
                    services.record('skill-learning-skipped', reason='unmeasured_training')
                    continue
                try:
                    proposals = []
                    minibatch = params['reflection_batch_size']
                    for offset in range(0, len(evidence), minibatch):
                        response = await services.complete('improver', EDIT_SYSTEM, encode({
                            'skill': current, 'training': evidence[offset:offset + minibatch],
                            'max_edits': params['edit_budget'], 'rejected_edits': rejected[-4:]}))
                        edits = json.loads(response)
                        apply_edits(current, edits, params['edit_budget'])
                        proposals.extend(edits)
                    edits = proposals
                    if len(proposals) > params['edit_budget'] or len(evidence) > minibatch:
                        response = await services.complete('improver', EDIT_SYSTEM, encode({
                            'instruction': 'Merge duplicates and conflicts, rank by usefulness, and return a bounded edit list.',
                            'skill': current, 'proposals': proposals, 'max_edits': params['edit_budget']}))
                        edits = json.loads(response)
                    candidate = apply_edits(current, edits, params['edit_budget'])
                    services.validate(candidate)
                except BudgetExhausted:
                    raise
                except (ValueError, TypeError, KeyError) as exc:
                    services.record('skill-edit-rejected', reason=str(exc))
                    continue
                if candidate == current:
                    continue
                selection = await services.evaluate(candidate, 'validation')
                passed = selection.score is not None and problem.policy.better(selection.score, score)
                services.record('skill-edit-gate', round=round_index, accepted=passed,
                    edits=edits, previous_score=score, selection_score=selection.score)
                if passed:
                    current, score = candidate, selection.score
                    accepted = [SearchCandidate(current, score, (('Acceptance', 'Strict selection improvement'),))]
                    candidate_training = await services.evaluate(current, 'train', cases=cases)
                    if await observe_candidate(services, current, candidate_training, selection):
                        reason = 'ready_for_confirmation'
                        break
                else:
                    rejected.append({'edits': edits, 'selection_score': selection.score})
        except BudgetExhausted:
            reason = 'budget_exhausted'
        return SearchResult(tuple(accepted), seed, reason)


def definition():
    from .registration import definition as build
    return build()


__all__ = ['SkillEditImprover', 'apply_edits', 'definition']
