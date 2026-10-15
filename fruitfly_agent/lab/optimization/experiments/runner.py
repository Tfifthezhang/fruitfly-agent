"""Original benchmark trials and text exercises share one bounded search budget."""
from uuid import uuid4

from fruitfly_agent.lab.algorithms.candidates import VersionCandidate, TargetRegistry
from fruitfly_agent.lab.algorithms.versions import SystemVersion, content_hash, canonical_json
from ..failure_processing.models import FailureExample
from ..failure_processing.projection import source_case, EvidenceProjection
from ..scoring import TaskPolicy
from ..services import NativeSearchServices, BudgetExhausted
from ..task_packs import FrozenTaskSuite
from .models import TaskRunEvidence


def original_policy():
    def unsupported(*_args):
        raise ValueError("original task references require their injected official executor")
    return TaskPolicy("official-task-reward-v1", "original-task-reference-v1", "official_reward",
        "isolated-official-task-v1", frozenset({"input", "expected"}), frozenset(), unsupported, unsupported,
        "Original tasks run in fresh external task environments with the official verifier.",
        learning_allowed=False)


class BenchmarkTaskSource:
    def __init__(self, tasks):
        self.tasks = tasks
        self.default_pack_id = "benchmark-experiment"

    def source_hash(self, pack_id):
        if pack_id != self.default_pack_id:
            raise ValueError("unknown frozen benchmark task set")
        return self.tasks.digest

    def holdout(self, pack_id):
        self.source_hash(pack_id)
        return tuple(source_case(t) for t in self.tasks.holdout)

    def freeze(self, pack_id, target_id):
        self.source_hash(pack_id)
        policy = original_policy()
        return FrozenTaskSuite(tuple(source_case(t) for t in self.tasks.train),
            tuple(source_case(t) for t in self.tasks.validation), self.tasks.digest, pack_id,
            "Frozen original benchmark tasks", self.tasks.digest, target_id, policy.policy_id,
            execution_id=policy.execution_id, evaluation_policy=policy,
            case_ids=tuple((source_case(t).case_id, t.task_id) for t in (*self.tasks.train, *self.tasks.validation)))


class TextChangeAdapter:
    def __init__(self, target, read_artifact):
        self.target, self.read_artifact = target, read_artifact

    def validate_change(self, change):
        if change.before != self.target.snapshot().content_hash:
            raise ValueError("text change baseline is stale")
        self.target.validate(self.read_artifact(change.after))


class BenchmarkSearchServices(NativeSearchServices):
    def __init__(self, *args, context, policy, **kwargs):
        super().__init__(*args, **kwargs)
        self.context, self.automatic_policy = context, policy
        self.tasks = {source_case(t).case_id: t for t in (*context.tasks.train, *context.tasks.validation, *context.tasks.holdout)}
        self.receipts = {}
        self.projection = EvidenceProjection()
        self.registry = TargetRegistry()
        self.registry.register("H", self.target.snapshot().target_id, "text-v1", TextChangeAdapter(self.target, context.read_artifact))
        self.environment_ids = {}
        self.instruction_ids = {}
        self.excluded_learning_inputs = tuple(t.instruction for t in (*context.tasks.validation, *context.tasks.holdout))

    async def execute_case(self, text, case, evaluation_id, **kwargs):
        if case.case_id not in self.tasks:
            return await super().execute_case(text, case, evaluation_id, **kwargs)
        task = self.tasks[case.case_id]
        packet = self.context.packet_for_text(text)
        version = SystemVersion.from_dict(packet["version"])
        if text != self.context.baseline:
            candidate = VersionCandidate.from_dict(packet.pop("candidate"))
            self.registry.validate(candidate, self.context.parent)
            if version != candidate.version:
                raise ValueError("trial packet differs from its declared candidate")
        elif version != self.context.parent:
            raise ValueError("baseline trial differs from the frozen parent version")
        calls = self.automatic_policy.external_trial_model_calls
        if self.budget.limits["model"] - self.budget.used["model"] < calls:
            self.budget.exhausted_kind = "model"
            raise BudgetExhausted("insufficient model allocation for a complete original-task trial")
        lease = uuid4().hex
        self.budget.used["model"] += calls
        packet.update(lease_id=lease, max_model_calls=calls, max_output_tokens=self.max_tokens,
                      instruction=task.instruction)
        self.record("external-trial-lease", evaluation_id=evaluation_id, lease_id=lease,
                    reserved_model_calls=calls, version=version.to_dict(), task_reference=task.reference_id)
        # Unknown/cancelled work retains the whole allocation. Only a validated
        # receipt can release unused calls; no unknown paid work is replayed.
        result = await self.context.executor.run(task, packet,
            timeout=self.automatic_policy.external_trial_timeout_seconds, signal=self.signal)
        receipt = TaskRunEvidence.from_dict(result["evidence"])
        if (receipt.task != task or receipt.version != version or receipt.conditions_id != packet["conditions_id"]
                or receipt.model_calls is None or receipt.model_calls > calls):
            raise ValueError("external task receipt does not match task, version, conditions or allocation")
        runtime_receipt = self.context.executor.runtime_receipt(result)
        if (runtime_receipt.get("lease_id") != lease or runtime_receipt.get("version") != version.to_dict()
                or runtime_receipt.get("conditions_id") != packet["conditions_id"]
                or runtime_receipt.get("model_calls") != receipt.model_calls
                or not receipt.runtime_digest or not receipt.environment_digest
                or (runtime_receipt.get("runtime") or {}).get("digest") != receipt.runtime_digest
                or content_hash(canonical_json(runtime_receipt.get("execution_environment"))) != receipt.environment_digest):
            raise ValueError("external task invocation receipt differs from its declared evidence")
        instruction_hash = runtime_receipt.get("instruction_hash")
        if not instruction_hash or self.instruction_ids.setdefault(task.reference_id, instruction_hash) != instruction_hash:
            raise ValueError("effective task instruction changed between trials")
        self.budget.used["model"] -= calls - receipt.model_calls
        if receipt.environment_digest:
            previous = self.environment_ids.setdefault(task.reference_id, receipt.environment_digest)
            if previous != receipt.environment_digest:
                raise ValueError("task environment changed between comparison trials")
        self.receipts[evaluation_id] = (receipt, result)
        self.record("external-trial-result", evaluation_id=evaluation_id, lease_id=lease,
                    evidence=receipt.to_dict(), evidence_root=result["evidence_root"])
        if receipt.status != "scored":
            raise ValueError("original task has no admissible official score: " + receipt.status)
        return receipt.output, receipt.score, receipt.feedback

    def failure_example(self, case, observation):
        receipt, result = self.receipts[observation.evaluation_id]
        material = self.projection.project(receipt,
            authorized={t.reference_id for t in self.context.tasks.train},
            load_artifact=lambda artifact: self.context.executor.read_evidence(result, artifact))
        return FailureExample(case, observation, material)
