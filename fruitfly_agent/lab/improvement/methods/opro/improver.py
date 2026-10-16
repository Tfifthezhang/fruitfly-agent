"""Native bounded OPRO: historical solutions and objective values drive proposals."""
import json
from .. import MethodUsage
from fruitfly_agent.lab.algorithms import Algorithm, AlgorithmSpec
from fruitfly_agent.lab.improvement.contracts.search import SearchCandidate, SearchResult, content_id
from fruitfly_agent.lab.improvement.runtime.services import BudgetExhausted
from fruitfly_agent.lab.improvement.methods.opro.prompts import SYSTEM_PROMPT, build_proposal_prompt


class OproImprover(Algorithm):
    usage = MethodUsage('Manual /improvement.', 'Training and selection tasks with explicit acceptance.',
        'Measured scores from task execution.', 'Configured improver model uses scored solution history.',
        'Selection scores; optional automatic workflow supplies independent holdout confirmation.',
        'Review and activate the H text candidate in a new session.')
    spec = AlgorithmSpec("opro", "opro-text-v2", "session")
    supported_schemas = frozenset({"text-v1"})
    required_capabilities = frozenset({"evaluate", "complete", "history"})
    supported_roles = frozenset({'H'})

    async def search(self, problem, services):
        if problem.baseline.role not in self.supported_roles:
            raise ValueError('OPRO currently supports H targets only')
        params = dict(problem.parameters)
        scored, seed, reason = [], None, "completed"
        seen = {content_id(problem.baseline.text)}
        try:
            baseline = await services.evaluate(problem.baseline.text, "validation")
            seed = baseline.score
            if seed is not None:
                scored.append((problem.baseline.text, seed))
            last_training = await services.evaluate(problem.baseline.text, "train")
            for round_index in range(params["rounds"]):
                services.check()
                history = sorted(scored, key=lambda c: problem.policy.utility(c[1]), reverse=True)[:params["history_limit"]]
                history.reverse()
                prompt = build_proposal_prompt(problem, history, last_training,
                                               candidate_count=params["batch_size"])
                try:
                    response = await services.complete("improver", SYSTEM_PROMPT, prompt)
                    texts = json.loads(response)
                    if not isinstance(texts, list) or not 1 <= len(texts) <= params["batch_size"] or not all(isinstance(t, str) for t in texts):
                        raise ValueError("invalid candidate array")
                except BudgetExhausted:
                    raise
                except Exception as exc:
                    services.record("proposal-error", round=round_index, error=type(exc).__name__)
                    continue
                for text in texts:
                    identity = content_id(text)
                    if identity in seen:
                        services.record("proposal-rejected", round=round_index, candidate_id=identity, reason="duplicate")
                        continue
                    seen.add(identity)
                    try:
                        services.validate(text)
                    except ValueError as exc:
                        services.record("proposal-rejected", round=round_index, candidate_id=identity, reason=str(exc))
                        continue
                    services.record("opro-proposal", round=round_index, candidate_id=identity, text=text)
                    train = last_training = await services.evaluate(text, "train")
                    selection = await services.evaluate(text, "validation")
                    services.record("opro-attempt", round=round_index, candidate_id=identity, text=text,
                                    training_score=train.score, selection_score=selection.score)
                    if train.score is not None and selection.score is not None:
                        scored.append((text, selection.score))
                        observer = getattr(services, "candidate_evaluated", None)
                        if observer is not None:
                            stop = await observer(text, train, selection)
                            if type(stop) is not bool:
                                raise ValueError("candidate observer must return a boolean")
                            if stop:
                                return SearchResult((SearchCandidate(text, selection.score),), seed,
                                                    "ready_for_confirmation")
        except BudgetExhausted:
            reason = "budget_exhausted"
        scored.sort(key=lambda c: problem.policy.utility(c[1]), reverse=True)
        return SearchResult(tuple(SearchCandidate(text, score) for text, score in scored
                                  if text != problem.baseline.text)[:3], seed, reason)
