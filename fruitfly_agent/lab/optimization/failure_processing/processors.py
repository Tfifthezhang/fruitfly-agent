"""Replaceable replay and model-distillation methods; neither owns candidate adoption."""
from __future__ import annotations

from dataclasses import asdict
import json

from .models import FailureExample, LearningMaterial, LearningTask
from ..scoring import builtin_task_policies


def _json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate material JSON field")
            result[key] = value
        return result
    if not isinstance(text, str) or len(text.encode("utf-8")) > 100000:
        raise ValueError("learning material exceeds 100 KB")
    def reject_constant(_):
        raise ValueError("nonfinite material value")
    return json.loads(text, object_pairs_hook=unique, parse_constant=reject_constant)


class ReplayFailureProcessor:
    implementation_id = "failure-replay-v1"

    async def process(self, failures, services, *, policy, limit):
        services.check()
        tasks = tuple(LearningTask(f.case, f.case.case_id, self.implementation_id,
                                  "Original task and acceptance retained", policy.policy_id,
                                  policy.execution_id) for f in failures[:limit])
        return LearningMaterial(tasks, self.implementation_id)


class ModelDistillationProcessor:
    implementation_id = "failure-distillation-v1"

    async def process(self, failures, services, *, policy, limit):
        services.check()
        sources = {}
        policies = {p.policy_id: p for p in builtin_task_policies()}
        if policy.learning_allowed:
            policies[policy.policy_id] = policy
        default_policy_id = policy.policy_id if policy.learning_allowed else "normalized-exact-v1"
        payload = {"task_schema": policy.task_schema,
                   "acceptance_fields": sorted(policy.required_fields - {"input"}),
                   "acceptance_example": policy.acceptance_example,
                   "learning_policies": [{"policy_id": p.policy_id, "task_schema": p.task_schema,
                       "acceptance_fields": sorted(p.required_fields - {"input"}),
                       "acceptance_example": p.acceptance_example} for p in policies.values()],
                   "limit": limit,
                   "failures": []}
        for failure in failures:
            row = {"source_case_id": failure.case.case_id, "task": asdict(failure.case),
                   "output": failure.observation.output, "score": failure.observation.score,
                   "feedback": failure.observation.feedback}
            if failure.material:
                row["source_evidence"] = _json(failure.material)
            tentative = {**payload, "failures": [*payload["failures"], row]}
            if len(json.dumps(tentative, ensure_ascii=False)) <= 60000:
                payload = tentative
                sources[failure.case.case_id] = failure
        if not sources:
            raise ValueError("no complete failure example fits the generation input budget")
        services.record("material-input", material_method=self.implementation_id, payload=payload)
        response = await services.complete("materializer",
            "Derive small, self-contained learning exercises from the supplied scored failures. "
            "You may simplify or vary tasks, but retain the source's intended requirements. "
            "Return only a JSON object with tasks: [{source_case_id, policy_id, input, acceptance}]. "
            "Choose a declared learning policy; the learning task need not have the original task type. "
            "Acceptance must use the declared fields. Do not generate evaluator code or imports.",
            json.dumps(payload, ensure_ascii=False))
        document = _json(response)
        if not isinstance(document, dict) or set(document) != {"tasks"}:
            raise ValueError("material generation needs only a tasks array")
        rows = document["tasks"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= limit:
            raise ValueError("material generation returned an invalid task count")
        tasks, seen = [], set()
        for row in rows:
            services.check()
            if (not isinstance(row, dict) or not {"source_case_id", "input", "acceptance"} <= row.keys()
                    or row.keys() - {"source_case_id", "input", "acceptance", "policy_id"}):
                raise ValueError("invalid generated learning task")
            source_id = row["source_case_id"]
            if not isinstance(source_id, str) or source_id not in sources:
                raise ValueError("learning task must reference an authorized failed training task")
            acceptance = row["acceptance"]
            learning_policy_id = row.get("policy_id", default_policy_id)
            if not isinstance(learning_policy_id, str) or learning_policy_id not in policies:
                raise ValueError("unknown learning policy")
            learning_policy = policies[learning_policy_id]
            learning_policy.check_available()
            required = learning_policy.required_fields - {"input"}
            allowed = required | learning_policy.optional_fields
            if not isinstance(acceptance, dict) or not required <= acceptance.keys() or acceptance.keys() - allowed:
                raise ValueError("generated acceptance differs from the registered policy")
            case = learning_policy.project({"input": row["input"], **acceptance})
            if case.case_id in seen:
                raise ValueError("duplicate generated learning task")
            seen.add(case.case_id)
            review_request = {"source": asdict(sources[source_id].case), "exercise": asdict(case),
                              "source_task_schema": policy.task_schema,
                              "learning_task_schema": learning_policy.task_schema}
            if sources[source_id].material:
                review_request["source_evidence"] = _json(sources[source_id].material)
            review = _json(await services.complete("material_reviewer",
                "Review this generated learning exercise independently of its generator. "
                "Check self-contained instructions, consistency with the source requirement, "
                "and whether every acceptance condition is justified by the exercise. "
                "Reject ambiguity, changed intent, contradictory tests or invented expectations. "
                "Return only {\"accepted\": true or false, \"reason\": \"...\"}. "
                "This review qualifies learning material only; it is not proof of task improvement.",
                json.dumps(review_request, ensure_ascii=False)))
            if (not isinstance(review, dict) or set(review) != {"accepted", "reason"}
                    or type(review["accepted"]) is not bool or not isinstance(review["reason"], str)
                    or not 1 <= len(review["reason"].strip()) <= 1000):
                raise ValueError("invalid learning material review")
            services.record("material-review", source_case_id=source_id, task_id=case.case_id,
                            accepted=review["accepted"], reason=review["reason"],
                            material_method=self.implementation_id)
            if review["accepted"]:
                tasks.append(LearningTask(case, source_id, self.implementation_id,
                                          "Model-reviewed learning exercise: " + review["reason"],
                                          learning_policy.policy_id, learning_policy.execution_id))
        if not tasks:
            raise ValueError("no generated learning exercises passed material review")
        return LearningMaterial(tuple(tasks), self.implementation_id)
