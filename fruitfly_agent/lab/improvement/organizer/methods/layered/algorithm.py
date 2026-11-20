"""Independent organizer Agent; all role output remains attributable derived text."""
from dataclasses import asdict
from typing import Any
import json
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.improvement.contracts.organization import EvidenceView
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from ...instructions import OrganizerInstructions
from ...workspace import build_workspace
from ...findings import validate_findings, FINDING_FIELDS, finding_sources
from ....evidence.session import EvidenceSession
from ....evidence.packets import reflection_packet
from .scheduling import schedule
from .extraction import extract
from ...publication import publish_investigation


class LayeredOrganizer:
    implementation_id = 'layered-organizer-v1'

    def __init__(self, config, artifacts, *, instructions=None, settings=None, runtime_factory=None, options=None):
        from ...registration import normalize
        options = normalize({'settings': options or {}})['settings']
        self.events_per_unit = options['events_per_unit']
        self.extraction_model_requests = options['extraction_model_requests']
        self.artifacts = artifacts
        self.instructions = instructions or OrganizerInstructions()
        self.session = EvidenceSession(config, artifacts, settings=settings, runtime_factory=runtime_factory)

    async def organize(self, request, services):
        return await services.operation(self._organize(request, services), stage='organizer')

    async def _organize(self, request, services):
        workspace, batch = build_workspace(request, self.artifacts, record=services.record)
        packet = reflection_packet(request, workspace, batch, {'findings': []})
        organized_queue = {}
        selection = next((resource for resource in request.context if resource.path == 'selection.json'), None)
        plan = json.loads(self.artifacts.read(selection.artifact_id)) if selection else {}
        if plan.get('implementation_id') == 'focused-group-material-v1' and plan.get('bounded', True):
            units = schedule(packet, workspace, self.events_per_unit)
            queue_receipt = self.artifacts.put(canonical_json({'units': units}).encode())
            services.record('organization-unit-queue', artifact_id=queue_receipt, count=len(units))
            paths = {}
            task_inputs = {card['task_id']: card['input'] for card in packet['cards']}
            extraction_ceiling = min(self.extraction_model_requests, self.session.settings.supply.max_pages)
            for unit in units:
                if unit['state'] == 'pending':
                    if workspace.access.budget['model_requests'] >= extraction_ceiling:
                        unit = {**unit, 'state': 'deferred_budget'}
                    else:
                        services.check()
                        try:
                            observations = await extract(self.session, self.instructions.extract, self.instructions.system,
                                                         unit, workspace, task_inputs[unit['task_id']], services,
                                                         model_request_ceiling=extraction_ceiling)
                            unit = {**unit, 'state': 'processed', 'observations': observations}
                        except (ValueError, RuntimeError) as exc:
                            state = ('deferred_budget' if 'evidence_request_budget_exhausted' in str(exc)
                                     else 'unavailable')
                            unit = {**unit, 'state': state, 'detail': str(exc)[:500]}
                path = 'units/' + unit['unit_id'][7:] + '.json'
                paths[path] = unit
                reference = self.artifacts.put(canonical_json(unit).encode())
                workspace.references['context/' + path] = reference
                services.record('organization-unit-retained', artifact_id=reference,
                                task_id=unit['task_id'], state=unit['state'])
            index = {'units': [{'path': 'context/' + path, 'task_id': unit['task_id'],
                               'artifact_id': workspace.references['context/' + path],
                               'state': unit['state']} for path, unit in paths.items()]}
            workspace.references['context/units.json'] = self.artifacts.put(canonical_json(index).encode())
            organized_queue = {'units.json': index, **paths}
            packet['coverage']['extraction_model_requests'] = workspace.access.budget['model_requests']
            packet['coverage']['extraction_model_request_limit'] = extraction_ceiling
            packet['coverage']['unit_states'] = {
                state: sum(unit['state'] == state for unit in paths.values())
                for state in sorted({unit['state'] for unit in paths.values()})}
        accepted = None
        source_rows: list[dict[str, Any]] = []
        def accept(value):
            nonlocal accepted, source_rows
            raw = value if isinstance(value, str) else canonical_json(value)
            reference = self.artifacts.put(raw.encode())
            services.record('organization-response', artifact_id=reference)
            data = json.loads(raw)
            if not isinstance(data, dict) or set(data) != {'schema_version', 'sections', 'findings'} or data.get('schema_version') != 2 or not isinstance(data['sections'], list):
                raise ValueError('organizer must submit sections and findings arrays')
            validate_findings(data['findings'])
            source_rows = []
            for index, section in enumerate(data['sections']):
                if set(section) != {'title', 'summary', 'sources'} or not all(
                        isinstance(section[k], str) and section[k].strip() for k in ('title', 'summary')):
                    raise ValueError('each readable section needs title, summary and sources')
                if not isinstance(section['sources'], list) or not section['sources']:
                    raise ValueError('summary requires attributable sources')
                for source in section['sources']:
                    if (set(source) != {'path', 'citation_id'} or source['path'] not in workspace.paths()
                            or source['citation_id'] not in workspace.eligible_paths(source['path'])):
                        raise ValueError(f'sections[{index}].sources: unavailable or unread evidence: {source}')
                    source_rows.append(source)
            for finding in data['findings']:
                if (set(finding['run_ids']) | set(finding['control_ids'])) - {r.run_id for r in request.records}:
                    raise ValueError('finding scope exceeds supplied executions')
                for source in finding_sources(finding):
                    if (set(source) != {'path', 'citation_id'} or source['path'] not in workspace.paths()
                            or source['citation_id'] not in workspace.eligible_paths(source['path'])):
                        raise ValueError('finding ' + finding['issue_id'] + ' cited unavailable or unread evidence: ' + source['path'])
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
        fact = {'type': 'object', 'properties': {'text': text,
            'sources': {'type': 'array', 'items': source}},
            'required': ['text', 'sources'], 'additionalProperties': False}
        gap = {'type': 'object', 'properties': {'question': text,
            'materials': {'type': 'array', 'items': text},
            'availability': {'type': 'string', 'enum': ['not_read', 'not_granted', 'unavailable', 'unknown']}},
            'required': ['question', 'materials', 'availability'], 'additionalProperties': False}
        finding = {'type': 'object', 'properties': {
            **{key: text for key in ('issue_id', 'signal')},
            'facts': {'type': 'array', 'items': fact, 'maxItems': 16},
            'unknowns': {'type': 'array', 'items': gap, 'maxItems': 16},
            **{key: {'type': 'array', 'items': text, 'maxItems': 16}
                for key in ('hypotheses', 'counterevidence', 'run_ids', 'control_ids')},
            'status': {'type': 'string', 'enum': ['ready_for_proposal', 'needs_evidence', 'not_supported']}},
            'required': list(FINDING_FIELDS), 'additionalProperties': False}
        tool = AgentTool(name='submit_organization', label='Submit readable view',
            description='Submit sourced facts, testable hypotheses, counterevidence and unknowns; no candidate edits.',
            parameters={'type': 'object', 'properties': {'schema_version': {'type': 'integer', 'enum': [2]}, 'sections': {'type': 'array', 'items': section},
                    'findings': {'type': 'array', 'items': finding, 'maxItems': 16}},
                'required': ['schema_version', 'sections', 'findings'], 'additionalProperties': False}, execute=submit, requires_exclusive_batch=True)
        async def check(ctx):
            nonlocal accepted, source_rows
            previous, previous_sources = accepted, source_rows
            errors = []
            try:
                for key in ('sections', 'findings'):
                    for index, item in enumerate(ctx.args[key]):
                        value = {**ctx.args, 'sections': [], 'findings': [], key: [item]}
                        try:
                            accept(value)
                        except (ValueError, TypeError, KeyError) as exc:
                            errors.append({'path': f'{key}[{index}]', 'error': str(exc)[:4000]})
                if not errors:
                    try:
                        accept(ctx.args)
                    except (ValueError, TypeError, KeyError) as exc:
                        errors.append({'path': 'submission', 'error': str(exc)[:4000]})
            finally:
                accepted, source_rows = previous, previous_sources
            if errors:
                return AgentToolResult([TextBlock(canonical_json({'valid': False, 'errors': errors}))])
            return AgentToolResult([TextBlock('Organization draft validated; submit_organization publishes it.')])
        check_tool = AgentTool(name='check_organization', label='Check organization draft',
            description='Validate a draft through the final owner validator without publishing or finishing.',
            parameters=tool.parameters, execute=check, requires_exclusive_batch=True)
        mission = self.instructions.organize
        if organized_queue:
            mission += ('\nUse context/units.json to find task-local extraction results and deferred units. '
                        'Read original spans before establishing detailed facts and report coverage gaps.')
        if request.instruction.strip():
            mission += '\n\nInvocation requirements:\n' + request.instruction
        await self.session.session(mission, workspace, services, system=self.instructions.system,
            extra_tools=(tool, check_tool), validate_final=accept,
            submission_result=lambda: canonical_json(accepted) if accepted is not None else None,
            initial_content=canonical_json({'batch_path': 'context/batch.json', 'task_count': len(request.tasks)}))
        if accepted is None:
            raise ValueError('organizer did not submit a view')
        if organized_queue:
            read_units = {path for path in workspace.access.inspection()['paths'] if path.startswith('context/units/')}
            cited_units = {source['path'] for source in source_rows if source['path'].startswith('context/units/')}
            packet['coverage']['unit_records_read_in_synthesis'] = len(read_units)
            packet['coverage']['unit_records_cited_in_synthesis'] = len(cited_units)
            packet['coverage']['unit_records_without_direct_citation'] = len(organized_queue['units.json']['units']) - len(cited_units)
        values = {**organized_queue, **publish_investigation(accepted, workspace, request.records),
            'batch.json': batch, 'guide.json': accepted,
            'reflection-packet.json': {**packet, 'group_findings': accepted['findings']},
            'parts.json': {'parts': list(workspace.retained_parts.values()),
                'scope': 'Selected/new child findings; directory coverage is not full original reading.'},
            'sources.json': {'sources': source_rows, 'scope': 'Derived summaries do not certify downstream original reading.'}}
        resources = tuple(Resource('organization/' + path, self.artifacts.put(canonical_json(value).encode()), 'application/json', 'diagnostic')
            for path, value in values.items())
        view = EvidenceView(resources, tuple(sorted(set(workspace.references.values()))), self.implementation_id,
            content_hash(canonical_json(asdict(self.instructions))))
        services.record('organization-result', identity=view.identity, instructions_id=view.instructions_id)
        return view
