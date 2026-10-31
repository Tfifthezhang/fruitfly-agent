"""Final model choice delegates to the shared dimension-based evaluator."""
from fruitfly_agent.improvement.contracts.assessment import SelectionDecision, AssessmentUnavailable
from .evaluator import ModelEvaluator
from .instructions import EvaluatorInstructions
from .completed import completed_input
from fruitfly_agent.lab.improvement.assessment.measured import measured_selection


class AgentSelector:
    def __init__(self, inspector, services):
        self.services, self.inspector = services, inspector
        self.evaluator: ModelEvaluator = getattr(inspector, 'evaluator', None) or ModelEvaluator(
            inspector.workspace_session.config, inspector.artifacts)

    async def select(self, task, records):
        inputs = []
        for record in records:
            try: inputs.append(completed_input(task, record, self.inspector.artifacts))
            except AssessmentUnavailable: pass
        try:
            data, reference = await self.evaluator.evaluate(task, records, self.services,
                inputs=tuple(inputs), incumbent=records[0].run_id)
            return SelectionDecision(data['choice'] or records[0].run_id, data['reason'],
                evidence_ids=tuple(data['evidence_ids']), comparison_id=reference)
        except AssessmentUnavailable:
            self.services.record('selection-invalid', reason='Insufficient evaluation evidence; baseline retained')
            return SelectionDecision(records[0].run_id, 'Evaluation unavailable; baseline retained')
