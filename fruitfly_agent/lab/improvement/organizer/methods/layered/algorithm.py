"""Independent organizer Agent; all role output remains attributable derived text."""
from dataclasses import asdict
import json
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.improvement.contracts.organization import EvidenceView
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from ...instructions import OrganizerInstructions
from ...workspace import build_workspace
from ....evidence.session import EvidenceSession


class LayeredOrganizer:
    implementation_id = 'layered-organizer-v1'

    def __init__(self, config, artifacts, *, instructions=None, settings=None):
        self.artifacts = artifacts
        self.instructions = instructions or OrganizerInstructions()
        self.session = EvidenceSession(config, artifacts, settings=settings)

    async def organize(self, request, services):
        return await services.operation(self._organize(request, services), stage='organizer')

    async def _organize(self, request, services):
        workspace, batch = build_workspace(request, self.artifacts, record=services.record)
        accepted = None
        source_rows = []
        def accept(value):
            nonlocal accepted, source_rows
            raw = value if isinstance(value, str) else canonical_json(value)
            reference = self.artifacts.put(raw.encode())
            services.record('organization-response', artifact_id=reference)
            data = json.loads(raw)
            if not isinstance(data, dict) or set(data) != {'sections'} or not isinstance(data['sections'], list):
                raise ValueError('organizer must submit exactly a sections array')
            source_rows = []
            for section in data['sections']:
                if set(section) != {'title', 'summary', 'sources'} or not all(
                        isinstance(section[k], str) and section[k].strip() for k in ('title', 'summary')):
                    raise ValueError('each readable section needs title, summary and sources')
                if not isinstance(section['sources'], list) or not section['sources']:
                    raise ValueError('summary requires attributable sources')
                for source in section['sources']:
                    if (set(source) != {'path', 'citation_id'} or source['path'] not in workspace.paths()
                            or source['citation_id'] not in workspace.provided_paths.get(source['path'], set())):
                        raise ValueError('organizer cited unavailable or unread evidence')
                    source_rows.append(source)
            accepted = data
        async def submit(ctx):
            accept(ctx.args)
            return AgentToolResult(content=[TextBlock('Readable evidence view retained.')], terminate=True)
        text = {'type': 'string'}
        source = {'type': 'object', 'properties': {'path': text, 'citation_id': text},
            'required': ['path', 'citation_id'], 'additionalProperties': False}
        section = {'type': 'object', 'properties': {'title': text, 'summary': text,
            'sources': {'type': 'array', 'items': source}},
            'required': ['title', 'summary', 'sources'], 'additionalProperties': False}
        tool = AgentTool(name='submit_organization', label='Submit readable view',
            description='Submit attributable navigation and summaries; no optimization advice.',
            parameters={'type': 'object', 'properties': {'sections': {'type': 'array', 'items': section}},
                'required': ['sections'], 'additionalProperties': False}, execute=submit, requires_exclusive_batch=True)
        mission = self.instructions.organize
        if request.instruction.strip():
            mission += '\n\nInvocation requirements:\n' + request.instruction
        await self.session.session(mission, workspace, services, system=self.instructions.system,
            extra_tools=(tool,), validate_final=accept,
            submission_result=lambda: canonical_json(accepted) if accepted is not None else None,
            initial_content=canonical_json({'batch_path': 'context/batch.json', 'task_count': len(request.tasks)}))
        if accepted is None:
            raise ValueError('organizer did not submit a view')
        values = {'batch.json': batch, 'guide.json': accepted,
            'sources.json': {'sources': source_rows, 'scope': 'Derived summaries do not certify downstream original reading.'}}
        resources = tuple(Resource('organization/' + path, self.artifacts.put(canonical_json(value).encode()), 'application/json', 'diagnostic')
            for path, value in values.items())
        view = EvidenceView(resources, tuple(sorted(set(workspace.references.values()))), self.implementation_id,
            content_hash(canonical_json(asdict(self.instructions))))
        services.record('organization-result', identity=view.identity, instructions_id=view.instructions_id)
        return view
