"""Completed-only assessment over facts; no execution or activation authority."""
from dataclasses import asdict, dataclass, replace
import asyncio
import json
from typing import Any

from fruitfly_agent.improvement.contracts.live import Assessment, EvidencePosition
from fruitfly_agent.improvement.contracts.assessment import AssessmentUnavailable
from fruitfly_agent.improvement.contracts.failures import IntegrityError
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.improvement.execution.facts import FACTS_PATH, read_facts
from .feedback import FeedbackProjection


@dataclass(frozen=True)
class CompletedInput:
    task: Any
    record: Any
    facts: Any
    facts_id: str

    @property
    def position(self):
        # A final snapshot position, not a fabricated live event sequence.
        return EvidencePosition(self.record.run_id, self.record.harness_id, 'completed', 0)

    @property
    def evidence_ids(self):
        return (self.facts_id, self.facts.output_id, *(r.artifact_id for r in self.facts.evidence))


def completed_input(task, record, artifacts):
    facts = read_facts(record, artifacts)
    if facts is None:
        raise AssessmentUnavailable('execution facts are unavailable')
    reference = next(r.artifact_id for r in record.artifacts if r.path == FACTS_PATH)
    return CompletedInput(task, record, facts, reference)


class CompletedAssessmentService:
    """One model evaluator for completed feedback and comparisons."""
    def __init__(self, *, config, artifacts, services, instructions=None, evidence_settings=None):
        from .instructions import EvaluatorInstructions
        from .evaluator import ModelEvaluator
        self.config, self.artifacts, self.services = config, artifacts, services
        self.instructions = instructions if isinstance(instructions, EvaluatorInstructions) else EvaluatorInstructions(**(instructions or {}).get('instructions', {}))
        self.evaluator = ModelEvaluator(config, artifacts, instructions=self.instructions, **(evidence_settings or {}))
        self.values = {}

    async def assess(self, task, record):
        value = completed_input(task, record, self.artifacts)
        from fruitfly_agent.improvement.contracts.live import DimensionJudgment, EvidenceFinding
        try:
            data, reference = await self.evaluator.evaluate(task, (record,), self.services, inputs=(value,))
            assessment = Assessment(value.position, self.evaluator.implementation_id, (), status='final', scope='execution',
                detail=data['reason'], facts_id=value.facts_id, evidence_ids=tuple(data['evidence_ids']),
                dimensions=tuple(DimensionJudgment(**d) for d in data['evaluations'][0]['dimensions']),
                findings=tuple(EvidenceFinding(**f) for f in data['evaluations'][0]['findings']))
        except (asyncio.CancelledError, IntegrityError):
            raise
        except Exception as exc:
            self.services.check()
            assessment = Assessment(value.position, self.evaluator.implementation_id, (), status='unavailable',
                scope='execution', detail=type(exc).__name__, facts_id=value.facts_id, evidence_ids=(value.facts_id,))
        self.values[record.run_id] = (assessment,)
        reference = self.artifacts.put(canonical_json(asdict(assessment)).encode())
        self.services.record('completed-assessment', run_id=record.run_id, status=assessment.status, evidence=reference)
        return replace(record, artifacts=(*record.artifacts, Resource('assessment.json', reference, 'application/json', 'diagnostic'))), (assessment,)

    async def compare(self, task, records, incumbent):
        from fruitfly_agent.improvement.contracts.search import ExplorationDecision
        eligible = tuple(r for r in records if r.status == 'completed')
        inputs = tuple(completed_input(task, r, self.artifacts) for r in eligible)
        data, reference = await self.evaluator.evaluate(task, eligible, self.services, inputs=inputs, incumbent=incumbent.run_id)
        return ExplorationDecision(data['choice'] or incumbent.run_id, data['reason'], tuple(data['evidence_ids']), 'process-guided')

    async def compare_batches(self, groups, incumbent):
        votes, evidence, reasons, references = [], [], [], []
        width = {len(values) for values in groups.values()}
        if len(width) != 1:
            raise AssessmentUnavailable('batch comparison requires paired tasks')
        for index in range(next(iter(width))):
            inputs = tuple(values[index] for values in groups.values())
            if len({v.record.task_id for v in inputs}) != 1:
                raise AssessmentUnavailable('batch comparison requires the same ordered tasks')
            data, reference = await self.evaluator.evaluate(inputs[0].task, tuple(v.record for v in inputs), self.services, inputs=inputs)
            references.append(reference)
            mapping = {values[index].record.run_id: key for key, values in groups.items()}
            votes.append(mapping.get(data['choice'], incumbent))
            evidence.extend(data['evidence_ids'])
            reasons.append(data['reason'])
        choice = votes[0] if votes and len(set(votes)) == 1 else incumbent
        result={'evaluation_id': choice, 'reason': '; '.join(reasons)[:4000], 'evidence_ids': sorted(set(evidence))}
        self.last_comparison_id=self.artifacts.put(canonical_json({'groups':list(groups),'result':result,'judgments':references}).encode())
        return result
