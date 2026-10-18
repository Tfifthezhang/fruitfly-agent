"""Host-owned one-shot confirmation, unavailable to candidate generators."""
from dataclasses import replace

from fruitfly_agent.lab.improvement.contracts.search import SearchResult, content_id
from .services import BudgetExhausted


def freeze_confirmation(suite, source):
    cases = tuple(source.holdout(suite.pack_id))
    if not cases:
        raise ValueError('this method requires independent holdout cases in the selected task pack')
    inputs = {c.input for c in (*suite.train, *suite.validation)}
    if any(c.input in inputs for c in cases):
        raise ValueError('confirmation cases must be disjoint from training and selection')
    if source.source_hash(suite.pack_id) != suite.source_hash:
        raise ValueError('task package changed while preparing confirmation')
    return cases


async def confirm_result(problem, services, result, cases, *, policy=None):
    """Test only the selection winner, and never retry another candidate on holdout."""
    if not result.candidates:
        return result
    candidate = max(result.candidates, key=lambda c: problem.policy.utility(c.score))
    if result.seed_score is None or not problem.policy.better(candidate.score, result.seed_score):
        return SearchResult((), result.seed_score, 'selection_not_improved')
    try:
        baseline = await services.run_cases(problem.baseline.text, cases, stage='confirmation', policy=policy)
        comparison = await services.run_cases(candidate.text, cases, stage='confirmation', policy=policy)
    except BudgetExhausted:
        return SearchResult((), result.seed_score, 'budget_exhausted')
    passed = (baseline.score is not None and comparison.score is not None
              and problem.policy.utility(comparison.score) >= problem.policy.utility(baseline.score)
              and len(baseline.observations) == len(comparison.observations) == len(cases)
              and all(a.case_id == b.case_id and a.status == b.status == 'ok'
                      and problem.policy.utility(b.score) >= problem.policy.utility(a.score)
                      for a, b in zip(baseline.observations, comparison.observations)))
    services.record('confirmation-result', candidate_id=content_id(candidate.text), passed=passed,
        baseline_score=baseline.score, candidate_score=comparison.score,
        rule='No aggregate or per-case regression on independent tasks; selection must improve.')
    if not passed:
        return SearchResult((), result.seed_score, 'confirmation_failed')
    return SearchResult((replace(candidate, evidence=(*candidate.evidence,
        ('Independent confirmation', 'Passed; no aggregate or per-case regression'),
        ('Confirmation baseline score', str(baseline.score)),
        ('Confirmation candidate score', str(comparison.score)),
        ('Confirmation cases', str(len(cases))))),), result.seed_score, 'confirmed')
