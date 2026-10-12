"""OPRO proposal instructions and frozen-problem rendering."""

import json

from ..search import Evaluation, OptimizationProblem


SYSTEM_PROMPT = (
    "Optimize the declared text target using historical solutions and their measured objective values. "
    "Return only a JSON array of new candidate strings, no Markdown."
)


def build_proposal_prompt(
    problem: OptimizationProblem,
    history: list[tuple[str, float]],
    training: Evaluation,
    *,
    candidate_count: int,
) -> str:
    return json.dumps({
        "direction": problem.direction,
        "objective": {"metric": problem.policy.metric, "direction": problem.policy.direction},
        "baseline": problem.baseline.text,
        "history": [{"text": text, "score": score} for text, score in history],
        "training_examples": [{"input": case.input, "expected": case.expected} for case in problem.train],
        "training_feedback": [
            {"input": case.input, "output": observation.output,
             "score": observation.score, "feedback": observation.feedback}
            for case, observation in zip(problem.train, training.observations)
        ],
        "candidate_count": candidate_count,
    }, ensure_ascii=False)
