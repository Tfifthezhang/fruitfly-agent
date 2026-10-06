"""Native bounded OPRO: historical solutions and objective values drive proposals."""
import json
from fruitfly_agent.lab.algorithms import Algorithm, AlgorithmSpec
from .search import SearchCandidate, SearchResult, content_id
from .services import BudgetExhausted


class OproOptimizer(Algorithm):
    spec = AlgorithmSpec("opro", "opro-text-v2", "session")
    supported_schemas = frozenset({"text-v1"})
    required_capabilities = frozenset({"evaluate", "complete", "history"})

    async def search(self, problem, services):
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
                prompt = json.dumps({"direction": problem.direction, "objective": {"metric": problem.policy.metric,
                    "direction": problem.policy.direction}, "baseline": problem.baseline.text,
                    "history": [{"text": text, "score": score} for text, score in history],
                    "training_examples": [{"input": c.input, "expected": c.expected} for c in problem.train],
                    "training_feedback": [{"input": c.input, "output": o.output, "score": o.score, "feedback": o.feedback}
                        for c, o in zip(problem.train, last_training.observations)],
                    "candidate_count": params["batch_size"]}, ensure_ascii=False)
                try:
                    response = await services.complete("optimizer",
                        "Optimize the declared text target using historical solutions and their measured objective values. "
                        "Return only a JSON array of new candidate strings, no Markdown.", prompt)
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
        except BudgetExhausted:
            reason = "budget_exhausted"
        scored.sort(key=lambda c: problem.policy.utility(c[1]), reverse=True)
        return SearchResult(tuple(SearchCandidate(text, score) for text, score in scored
                                  if text != problem.baseline.text)[:3], seed, reason)
