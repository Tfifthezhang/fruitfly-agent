"""Evidence-grounded pending lessons; no publication authority."""
import json
from fruitfly_agent.improvement.contracts.editing import CompositionRequest
from fruitfly_agent.improvement.contracts.plans import ExperienceEntry
from ..evidence import EvidenceWorkspace

class AgentReflector:
    def __init__(self, editor, services):
        self.inspector, self.services = editor, services

    async def reflect(self, outcome):
        request = CompositionRequest(outcome.plan, outcome.task,
            outcome.candidates[0].base if outcome.candidates else outcome.harness,
            outcome.candidates, outcome.records, 0)
        workspace = EvidenceWorkspace.build(request, self.inspector.artifacts, record=self.services.record)
        response = await self.inspector.session(
            self.inspector.instructions.reflect,
            workspace, self.services, writable=False)
        if response.strip() == 'NO_ENTRY':
            return ()
        value = json.loads(response)
        cited = [r for r in outcome.records if r.run_id in value['evidence_ids'] and r.status == 'completed']
        if len({r.harness_id for r in cited}) < 2 or len(cited) != len(set(value['evidence_ids'])):
            raise ValueError('a lesson requires observed contrasts from distinct executed harnesses')
        return (ExperienceEntry('experience-' + outcome.plan.job_id, outcome.task.task_id,
            value['cue'], value['lesson'], tuple(value['evidence_ids']), outcome.harness, value.get('limitations', '')),)

