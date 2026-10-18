"""Archive-conditioned generation, reflection and measured workflow search."""
import json

from fruitfly_agent.lab.algorithms import Algorithm, AlgorithmSpec
from fruitfly_agent.lab.improvement.contracts.search import SearchCandidate, SearchResult, content_id
from fruitfly_agent.lab.improvement.runtime.services import BudgetExhausted
from .. import MethodUsage
from ..evidence import check_problem, encode, training_evidence, observe_candidate

SYSTEM = ('Design a bounded execution workflow for the frozen task domain. Return only JSON '
    '{"steps":["first stage instruction", "next stage instruction"]}, with 1–6 stages. '
    'Stages may solve, critique, compare and revise. The last stage must return only the final task answer. '
    'Use reusable instructions, never embed task-specific answers. No Python code.')


class WorkflowSearchImprover(Algorithm):
    spec = AlgorithmSpec('workflow-search', 'archive-workflow-search-v1', 'session')
    supported_roles = frozenset({'H'})
    supported_schemas = frozenset({'execution-workflow-v1'})
    required_capabilities = frozenset({'evaluate', 'complete', 'history'})
    usage = MethodUsage('Explicit /improvement on Execution workflow.',
        'Frozen training and selection tasks and a bounded stage workflow.',
        'Measured task outcomes, training feedback and executable schema errors.',
        'Archive-conditioned workflow design, self-reflection and bounded repair.',
        'Publish only a workflow that strictly beats the initial selection score.',
        'Review and activate the workflow in a new session; every stage is a normal model turn.')

    async def search(self, problem, services):
        check_problem(problem, self.supported_roles, self.supported_schemas)
        params, archive, candidates, seed = dict(problem.parameters), [], [], None
        seen, reason = {content_id(encode(json.loads(problem.baseline.text)))}, 'completed'
        try:
            baseline = await services.evaluate(problem.baseline.text, 'validation')
            seed = baseline.score
            if seed is None:
                return SearchResult((), None, 'baseline_unmeasured')
            training = await services.evaluate(problem.baseline.text, 'train')
            archive.append({'workflow': problem.baseline.text, 'score': seed})
            for round_index in range(params['rounds']):
                services.check()
                try:
                    text = await services.complete('improver', SYSTEM, encode({
                        'archive': archive[-params['archive_limit']:],
                        'training_tasks': [c.input for c in problem.train],
                        'training_evidence': training_evidence(training, problem.train), 'guidance': problem.direction,
                        'instruction': 'Invent a useful new design; reuse or combine promising prior designs.'}))
                    for _ in range(params['reflection_steps']):
                        text = await services.complete('improver', SYSTEM, encode({
                            'workflow': text, 'instruction': 'Review correctness, novelty and unnecessary stages; return the improved workflow.'}))
                    for attempt in range(params['repair_attempts'] + 1):
                        try:
                            services.validate(text)
                            break
                        except ValueError as exc:
                            if attempt == params['repair_attempts']:
                                raise
                            text = await services.complete('improver', SYSTEM, encode({'workflow': text, 'schema_error': str(exc)}))
                except BudgetExhausted:
                    raise
                except (ValueError, TypeError) as exc:
                    services.record('workflow-proposal-rejected', reason=str(exc))
                    continue
                # Whitespace changes do not create a new workflow design.
                identity = content_id(encode(json.loads(text)))
                if identity in seen:
                    continue
                seen.add(identity)
                training = await services.evaluate(text, 'train')
                selection = await services.evaluate(text, 'validation')
                services.record('workflow-design', round=round_index, text=text,
                    training_score=training.score, selection_score=selection.score)
                if training.score is None or selection.score is None:
                    continue
                archive.append({'workflow': text, 'score': selection.score})
                if problem.policy.better(selection.score, seed):
                    candidates.append(SearchCandidate(text, selection.score, (('Workflow format', 'Bounded declarative stages'),)))
                    if await observe_candidate(services, text, training, selection):
                        reason = 'ready_for_confirmation'
                        break
        except BudgetExhausted:
            reason = 'budget_exhausted'
        candidates.sort(key=lambda c: problem.policy.utility(c.score), reverse=True)
        return SearchResult(tuple(candidates[:3]), seed, reason)


def definition():
    from .registration import definition as build
    return build()


__all__ = ['WorkflowSearchImprover', 'definition']
