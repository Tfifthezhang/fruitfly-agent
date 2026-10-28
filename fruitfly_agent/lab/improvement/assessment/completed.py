"""Completed-only assessment over facts; no execution or activation authority."""
from dataclasses import asdict, dataclass, replace
import asyncio
import json
from typing import Any

from fruitfly_agent.core.data_model import ProviderView, UserMessage
from fruitfly_agent.improvement.contracts.live import Assessment, EvidencePosition, Metric
from fruitfly_agent.improvement.contracts.assessment import AssessmentUnavailable
from fruitfly_agent.improvement.contracts.search import ExplorationDecision
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.improvement.execution.facts import FACTS_PATH, read_facts
from fruitfly_agent.improvement.workflow.budget import AllocationExhausted
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
    def __init__(self, settings, *, config, artifacts, services, registry, instructions=None):
        self.settings, self.config, self.artifacts, self.services = settings, config, artifacts, services
        self.registry = registry
        self.instructions = dict(instructions or {})
        self.model_calls = 0
        self.values = {}
        self.feedback = FeedbackProjection(include_detail=True, all_metrics=True)
        self.assessors = tuple(registry.create(name, self, own=services.own) for name in settings.assessors)

    async def complete(self, instruction, payload):
        self.services.check()
        body = canonical_json(payload)
        if len(body.encode('utf-8')) > 2_000_000:
            raise AssessmentUnavailable('complete assessment input exceeds its allocation')
        if self.model_calls >= self.settings.max_model_calls:
            raise AssessmentUnavailable('process-assessment model allowance exhausted')
        self.services.reserve('model')
        self.model_calls += 1
        self.services.record('assessor-model-request', model=self.config.model, purpose='completed-process-assessment')
        view = ProviderView(instruction, [UserMessage(content=body)], [],
            self.config.model, self.config.max_tokens)
        async def request():
            stream = self.config.provider(view, signal=self.services.signal)
            try:
                return await stream.result()
            finally:
                await stream.aclose()
        result = await self.services.operation(asyncio.wait_for(
            request(), self.settings.timeout_seconds))
        if result.stop_reason != 'stop' or result.tool_calls or result.continue_turn:
            raise ValueError('completed assessor needs a tool-free final result')
        return json.loads(result.text)

    def render(self, inputs):
        rows = []
        size = 0
        for value in inputs:
            evidence = []
            resources = (*value.facts.evidence, Resource('output.txt', value.facts.output_id))
            seen = set()
            for resource in resources:
                if resource.artifact_id in seen:
                    continue
                seen.add(resource.artifact_id)
                data = self.artifacts.read(resource.artifact_id)
                size += len(data)
                if size > 2_000_000:
                    raise AssessmentUnavailable('complete granted evidence exceeds assessor input allocation')
                try:
                    body = data.decode('utf-8')
                except UnicodeDecodeError:
                    body = None
                evidence.append({'path': resource.path, 'artifact_id': resource.artifact_id,
                    'media_type': resource.media_type, 'content': body, 'size_bytes': len(data)})
            rows.append({'task': value.task.instruction, 'facts_id': value.facts_id, 'facts': value.facts.to_dict(), 'evidence': evidence,
                'assessments': [asdict(a) for a in self.values.get(value.record.run_id, ())]})
        return {'task': inputs[0].task.instruction, 'executions': rows}

    async def assess(self, task, record):
        if not self.assessors:
            return record, ()
        value = completed_input(task, record, self.artifacts)
        assessments = []
        for assessor in self.assessors:
            try:
                assessment = await self.services.operation(asyncio.wait_for(
                    assessor.assess(value), self.settings.timeout_seconds))
                self.validate(assessment, value, assessor.assessor_id)
                assessment = self.feedback.project(assessment)
            except (AllocationExhausted, asyncio.CancelledError):
                raise
            except Exception as exc:
                self.services.check()
                assessment = Assessment(value.position, assessor.assessor_id, (), status='unavailable',
                    scope='execution', detail=type(exc).__name__, facts_id=value.facts_id,
                    evidence_ids=(value.facts_id,))
            assessments.append(assessment)
            self.services.record('completed-assessment', run_id=record.run_id,
                assessor_id=assessment.assessor_id, status=assessment.status,
                evidence=self.artifacts.put(canonical_json(asdict(assessment)).encode()))
        self.values[record.run_id] = tuple(assessments)
        reference = self.artifacts.put(canonical_json([asdict(a) for a in assessments]).encode())
        return replace(record, artifacts=(*record.artifacts,
            Resource('process-assessments.json', reference, 'application/json', 'diagnostic'))), tuple(assessments)

    @staticmethod
    def validate(assessment, value, assessor_id):
        if (assessment.position != value.position or assessment.assessor_id != assessor_id
                or assessment.facts_id != value.facts_id or assessment.visibility != 'development'
                or assessment.scope != 'execution' or assessment.status != 'final'
                or set(assessment.evidence_ids) - set(value.evidence_ids)):
            raise ValueError('completed assessment differs from granted facts or identity')

    def ensure_available(self):
        if self.settings.required and any(a.status != 'final' for values in self.values.values() for a in values):
            raise AssessmentUnavailable('required completed assessment is unavailable')

    async def compare(self, task, records, incumbent):
        eligible = tuple(r for r in records if r.status == 'completed'
            and any(a.status == 'final' for a in self.values.get(r.run_id, ())))
        assessors = tuple(a for a in self.assessors if callable(getattr(a, 'compare', None)))
        if len(eligible) < 2 or not assessors:
            raise AssessmentUnavailable('completed comparison evidence is insufficient')
        inputs = tuple(completed_input(task, r, self.artifacts) for r in eligible)
        try:
            decision = await self.services.operation(asyncio.wait_for(
                assessors[0].compare(inputs, incumbent.run_id), self.settings.timeout_seconds))
            if (decision.run_id not in {r.run_id for r in eligible}
                    or set(decision.evidence_ids) - {v for i in inputs for v in i.evidence_ids}
                    or not decision.evidence_ids):
                raise ValueError('exploration comparison cited unavailable execution evidence')
            return decision
        except (AllocationExhausted, asyncio.CancelledError):
            raise
        except Exception as exc:
            self.services.check()
            raise AssessmentUnavailable(type(exc).__name__) from exc
