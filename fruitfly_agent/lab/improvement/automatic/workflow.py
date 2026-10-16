"""Bounded feedback-driven search; independent confirmation stops at human review."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, replace
import json
import math
import unicodedata

from ..failure_processing import FailureExample, LearningMaterial
from fruitfly_agent.lab.improvement.contracts.search import Evaluation, SearchCandidate, SearchResult, TrialObservation, content_id
from fruitfly_agent.lab.improvement.runtime.services import BudgetExhausted
from fruitfly_agent.lab.improvement.tasks.scoring import TaskPolicy, builtin_task_policies


@dataclass(frozen=True)
class AutomaticPolicy:
    min_improvement: float = 0.05
    max_case_regression: float = 0.0
    failure_threshold: float = 1.0
    material_limit: int = 4
    confirmation_repeats: int = 1
    timeout_seconds: float = 600.0
    external_trial_model_calls: int = 24
    external_trial_timeout_seconds: int = 1800
    external_timeout_seconds: int = 14400

    def __post_init__(self):
        for value in (self.min_improvement, self.max_case_regression,
                      self.failure_threshold, self.timeout_seconds):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("automatic policy numbers must be finite")
        if self.min_improvement <= 0 or self.max_case_regression < 0 or self.timeout_seconds <= 0:
            raise ValueError("invalid automatic improvement, regression or timeout policy")
        if type(self.material_limit) is not int or not 1 <= self.material_limit <= 12:
            raise ValueError("material limit must be 1–12")
        if type(self.confirmation_repeats) is not int or not 1 <= self.confirmation_repeats <= 5:
            raise ValueError("confirmation repeats must be 1–5")
        for value in (self.external_trial_model_calls, self.external_trial_timeout_seconds, self.external_timeout_seconds):
            if type(value) is not int or value < 1:
                raise ValueError("external trial limits must be positive integers")


@dataclass(frozen=True)
class PreparedMaterial:
    holdout: tuple
    policy: TaskPolicy
    source_hash: str
    case_ids: tuple[tuple[str, str], ...]


def _input_key(text):
    return unicodedata.normalize("NFC", text).strip()


class LearningSearchServices:
    """Only learning and original selection capabilities are exposed to a strategy."""
    def __init__(self, root, problem, baseline, observer, learning_tasks, policies):
        self.root, self.problem, self.baseline, self.observer = root, problem, baseline, observer
        self.stop, self.signal = root.stop, root.signal
        self.tasks = {t.case.case_id: t for t in learning_tasks}
        self.policies = policies

    def check(self):
        self.root.check()

    def validate(self, text):
        self.root.validate(text)

    def record(self, kind, **fields):
        return self.root.record(kind, **fields)

    def history(self):
        return tuple(r for r in self.root.history() if r.get("stage") != "confirmation")

    async def complete(self, role, system, prompt):
        return await self.root.complete(role, system, prompt)

    async def agent(self, role, system, prompt, *, files, output_path):
        return await self.root.agent(role, system, prompt, files=files, output_path=output_path)

    async def evaluate(self, text, partition, *, cases=None):
        self.check()
        if partition == "validation":
            if text == self.problem.baseline.text and cases is None:
                return self.baseline
            return await self.root.evaluate(text, partition, cases=cases)
        if partition != "train":
            raise ValueError("unknown learning search partition")
        selected = tuple(cases) if cases is not None else self.problem.train
        if not selected or any(c not in self.problem.train for c in selected):
            raise ValueError("learning task is outside the frozen material")
        observations = []
        for case in selected:
            task = self.tasks[case.case_id]
            policy = self.policies[task.policy_id or self.problem.policy.policy_id]
            result = await self.root.run_cases(text, (case,), stage="learning", policy=policy)
            for o in result.observations:
                observations.append(TrialObservation(o.evaluation_id, o.candidate_id, o.case_id,
                    "train", policy.execution_id, policy.policy_id, o.status, o.score, o.output,
                    ("Learning policy " + policy.policy_id + ": " + o.feedback)[:1000]))
        score = (sum(o.score for o in observations if o.score is not None) / len(observations)
                 if all(o.status == "ok" and o.score is not None for o in observations) else None)
        return Evaluation(text, tuple(observations), score)

    async def candidate_evaluated(self, text, training, selection):
        return await self.observer(text, selection)


class AutomaticWorkflow:
    implementation_id = "automatic-text-search-v1"

    def __init__(self, processor, policy=None):
        self.processor = processor
        self.policy = policy or AutomaticPolicy()

    def prepare(self, suite, source):
        if suite.evaluation_policy is None:
            raise ValueError("automatic search requires a declared task policy")
        if source.source_hash(suite.pack_id) != suite.source_hash:
            raise ValueError("task package changed before automatic preparation")
        holdout = tuple(source.holdout(suite.pack_id))
        if not holdout:
            raise ValueError("automatic search requires independent holdout tasks")
        if source.source_hash(suite.pack_id) != suite.source_hash:
            raise ValueError("task package changed while preparing confirmation")
        return PreparedMaterial(holdout, suite.evaluation_policy, suite.source_hash, suite.case_ids)

    def preview(self, suite, prepared):
        p = self.policy
        minimum = 2 * (len(suite.train) + len(suite.validation) + 1) + 2 * len(prepared.holdout) * p.confirmation_repeats
        return (("Workflow", "Automatic search; confirmed improvement waits for human adoption"),
                ("Failure processing", self.processor.implementation_id),
                ("Learning exercise limit", str(p.material_limit)),
                ("Minimum score gain", str(p.min_improvement)),
                ("Maximum per-case regression", str(p.max_case_regression)),
                ("Independent cases", str(len(prepared.holdout))),
                ("Independent repeats", str(p.confirmation_repeats)),
                ("Minimum trials for one candidate", str(minimum)),
                ("Workflow timeout seconds", str(p.timeout_seconds)))

    async def search(self, strategy, problem, services, prepared):
        seed = None
        try:
            async with asyncio.timeout(self.policy.timeout_seconds):
                return await self._search(strategy, problem, services, prepared)
        except BudgetExhausted:
            reason = "budget_exhausted"
        except TimeoutError:
            reason = "workflow_timeout"
        services.record("automatic-stop", reason=reason)
        services.set_phase("Automatic search stopped: " + reason.replace("_", " "))
        return SearchResult((), seed, reason)

    async def _search(self, strategy, problem, services, prepared):
        services.record("automatic-policy", workflow=self.implementation_id,
                        automatic_policy=asdict(self.policy), source_hash=prepared.source_hash,
                        original_case_ids=dict(prepared.case_ids))
        baseline_selection = await services.evaluate(problem.baseline.text, "validation")
        baseline_training = await services.evaluate(problem.baseline.text, "train")
        seed = baseline_selection.score
        if seed is None or baseline_training.score is None:
            return self._stop(services, seed, "baseline_unavailable")
        failure_example = getattr(services, "failure_example", FailureExample)
        failures = tuple(failure_example(case, observation) for case, observation in
            zip(problem.train, baseline_training.observations)
            if (observation.status == "ok" and observation.score is not None
                and (observation.score < self.policy.failure_threshold if problem.policy.direction == "max"
                     else observation.score > self.policy.failure_threshold)))
        if not failures:
            return self._stop(services, seed, "no_scored_failures")
        services.set_phase("Preparing learning material")
        material = await self.processor.process(failures, services, policy=prepared.policy,
                                                limit=self.policy.material_limit)
        self._validate_material(material, failures, problem, prepared,
                                extra_excluded=getattr(services, "excluded_learning_inputs", ()))
        material_record = services.record("learning-material", material_method=material.method_id,
            tasks=[{"task_id": t.task_id, "source_case_id": t.source_case_id,
                    "method_id": t.method_id, "review": t.review, "case": asdict(t.case),
                    "learning_policy_id": t.policy_id, "learning_execution_id": t.execution_id} for t in material.tasks])
        learning_cases = tuple(t.case for t in material.tasks)
        material_hash = content_id(json.dumps([asdict(t) for t in material.tasks], sort_keys=True))
        learning_problem = replace(problem, train=learning_cases)
        eligible = []
        observed_candidates = set()

        async def candidate_ready(text, selection):
            observed_candidates.add(content_id(text))
            if selection.score is None or not self._gain(problem, selection.score, seed):
                return False
            original_training = await services.evaluate(text, "train")
            if not self._no_regression(problem, baseline_training.observations, original_training.observations):
                services.record("automatic-candidate-rejected", candidate_id=content_id(text),
                                reason="original_training_regression_or_missing")
                return False
            eligible.append(SearchCandidate(text, selection.score))
            return True

        policies = {p.policy_id: p for p in builtin_task_policies()}
        policies[prepared.policy.policy_id] = prepared.policy
        search_services = LearningSearchServices(services, learning_problem, baseline_selection,
                                                candidate_ready, material.tasks, policies)
        result = await strategy.search(learning_problem, search_services)
        services.check_cancellation()
        if not eligible:
            # Other injected strategies need not implement the optional early-stop callback.
            for candidate in result.candidates:
                if content_id(candidate.text) in observed_candidates:
                    continue
                # A strategy's reported score may use its own objective or subset.
                # Only the unchanged original selection suite can qualify it.
                selection = await services.evaluate(candidate.text, "validation")
                if await candidate_ready(candidate.text, selection):
                    break
        if not eligible:
            return self._stop(services, seed, result.stop_reason if result.stop_reason == "budget_exhausted" else "no_improvement")
        candidate = eligible[0]
        # The same holdout is checked only once per job, after generation stops.
        services.record("confirmation-start", candidate_id=content_id(candidate.text),
                        count=len(prepared.holdout), repeats=self.policy.confirmation_repeats)
        before = await services.run_cases(problem.baseline.text, prepared.holdout,
            stage="confirmation", repeats=self.policy.confirmation_repeats)
        after = await services.run_cases(candidate.text, prepared.holdout,
            stage="confirmation", repeats=self.policy.confirmation_repeats)
        services.check_cancellation()
        passed = (before.score is not None and after.score is not None
                  and self._gain(problem, after.score, before.score)
                  and self._no_regression(problem, before.observations, after.observations))
        services.record("confirmation-result", candidate_id=content_id(candidate.text),
                        passed=passed, baseline_score=before.score, candidate_score=after.score,
                        source_hash=prepared.source_hash)
        if not passed:
            return self._stop(services, seed, "confirmation_failed")
        services.set_phase("Confirmed improvement ready for human review")
        evidence = (("Independent confirmation", "passed; adoption requires human review"),
                    ("Confirmation baseline score", str(before.score)),
                    ("Confirmation candidate score", str(after.score)),
                    ("Confirmation repeats", str(self.policy.confirmation_repeats)),
                    ("Confirmation task package hash", prepared.source_hash),
                    ("Failure processing", material.method_id),
                    ("Learning material hash", material_hash),
                    ("Learning material record", material_record),
                    ("Workflow implementation", self.implementation_id))
        return SearchResult((replace(candidate, evidence=evidence),), seed, "confirmed_improvement")

    def _validate_material(self, material, failures, problem, prepared, *, extra_excluded=()):
        if not isinstance(material, LearningMaterial) or len(material.tasks) > self.policy.material_limit:
            raise ValueError("invalid or over-limit learning material")
        allowed = {f.case.case_id for f in failures}
        policies = {p.policy_id: p for p in builtin_task_policies()}
        policies[prepared.policy.policy_id] = prepared.policy
        excluded = {_input_key(c.input) for c in (*problem.validation, *prepared.holdout)}
        excluded.update(_input_key(value) for value in extra_excluded)
        inputs = set()
        for task in material.tasks:
            key = _input_key(task.case.input)
            if task.source_case_id not in allowed or key in excluded or key in inputs:
                raise ValueError("learning material has unauthorized provenance or overlapping inputs")
            policy = policies.get(task.policy_id or prepared.policy.policy_id)
            if policy is None or task.execution_id and task.execution_id != policy.execution_id:
                raise ValueError("learning task policy or execution identity mismatch")
            inputs.add(key)

    def _gain(self, problem, candidate, baseline):
        return problem.policy.utility(candidate) - problem.policy.utility(baseline) >= self.policy.min_improvement

    def _no_regression(self, problem, before, after):
        if not before or len(before) != len(after):
            return False
        for old, new in zip(before, after):
            if (old.case_id != new.case_id or old.status != "ok" or new.status != "ok"
                    or old.score is None or new.score is None
                    or problem.policy.utility(old.score) - problem.policy.utility(new.score) > self.policy.max_case_regression):
                return False
        return True

    @staticmethod
    def _stop(services, seed, reason):
        services.record("automatic-stop", reason=reason)
        services.set_phase("Automatic search stopped: " + reason.replace("_", " "))
        return SearchResult((), seed, reason)
