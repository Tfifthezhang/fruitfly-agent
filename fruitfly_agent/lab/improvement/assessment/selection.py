"""Read-only output selection through an independently injected inspector."""
import json
from fruitfly_agent.improvement.contracts.pipeline import HarnessSnapshot, ComponentDocument, SelectionDecision, canonical_json
from ..evidence import EvidenceWorkspace


from fruitfly_agent.lab.improvement.assessment.measured import measured_selection

class AgentSelector:
    def __init__(self, editor, services):
        self.inspector, self.services = editor, services

    async def select(self, task, records):
        placeholder = HarnessSnapshot((ComponentDocument('selection', 'selection', 'H', 'selection-v1', ()),))
        files = {'context/task.md': task.instruction.encode('utf-8')}
        mapping = {}
        for index, record in enumerate(records):
            label = str(index + 1)
            mapping[label] = record.run_id
            files[f'context/candidates/{label}/output.txt'] = record.output.encode('utf-8')
            for resource in record.artifacts:
                if resource.kind == 'deliverable':
                    files[f'context/candidates/{label}/' + resource.path] = self.inspector.artifacts.read(resource.artifact_id)
        for resource in task.inputs:
            files['context/inputs/' + resource.path] = self.inspector.artifacts.read(resource.artifact_id)
        files['INDEX.json'] = canonical_json({'files': sorted(files), 'candidate_ids': list(mapping)}).encode('utf-8')
        workspace = EvidenceWorkspace(baseline=placeholder, files=files, writable_ids=())
        response = await self.inspector.session(
            self.inspector.instructions.select,
            workspace, self.services, writable=False)
        try:
            if response.strip() == 'NO_CLEAR_CHOICE':
                return SelectionDecision(records[0].run_id, 'Insufficient distinction; baseline retained')
            value = json.loads(response)
            return SelectionDecision(mapping[value['choice']], value['reason'])
        except (ValueError, TypeError, KeyError):
            self.services.record('selection-invalid', reason='Malformed choice; baseline retained')
            return SelectionDecision(records[0].run_id, 'Invalid selection; baseline retained')

