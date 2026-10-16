"""Project authorized training evidence into bounded, source-attributed material."""
import json
from fruitfly_agent.lab.improvement.contracts.search import TaskCase
from ..experiments.models import TaskRunEvidence
from fruitfly_agent.lab.improvement.contracts.versions import canonical_json


def source_case(task):
    # The case is an immutable handle, not a single-turn approximation of the task.
    return TaskCase("Original benchmark task " + task.task_id + "\nReference: " + task.reference_id,
                    "Official verification: " + task.verifier_id, task.reference_id)


class EvidenceProjection:
    implementation_id = "training-evidence-projection-v1"

    def project(self, evidence: TaskRunEvidence, *, authorized, load_artifact):
        if evidence.task.reference_id not in authorized or evidence.status != "scored":
            raise ValueError("only authorized scored training evidence can become learning material")
        if len(evidence.task.instruction) > 40000:
            raise ValueError("complete instructions exceed the material projection bound")
        steps = []
        for artifact in evidence.artifacts:
            if artifact.kind != "trajectory":
                continue
            raw = load_artifact(artifact)
            for index, line in enumerate(raw.splitlines()):
                record = json.loads(line)
                # Keep canonical message records, never configuration, keys or hidden verifier files.
                if record.get("type") == "message" and isinstance(record.get("message"), dict):
                    body = canonical_json(record["message"])
                    steps.append({"source": artifact.digest, "line": index + 1,
                                  "message": body[:1600], "truncated": len(body) > 1600})
        payload = {"source_task": evidence.task.to_dict(), "run_id": evidence.run_id,
                   "score": evidence.score, "feedback": evidence.feedback[:1000],
                   "output": evidence.output[:4000], "trajectory_excerpt": steps[-6:],
                   "trajectory_total_messages": len(steps),
                   "version": evidence.version.to_dict() if evidence.version else None,
                   "conditions_id": evidence.conditions_id}
        return canonical_json(payload)
