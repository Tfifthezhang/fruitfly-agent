"""Explicit discovery/delivery of still-authorized historical child findings."""
import hashlib
import json
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.improvement.contracts.organization import OrganizationPart
from fruitfly_agent.improvement.contracts.versions import canonical_json, require_hash
from .catalog import WorkspaceEvidence
from .resources import ReferenceWorkspace


class OrganizationPartCache:
    def __init__(self, workspace, artifacts, settings, store, *, conditions, models, workers, record):
        self.workspace, self.artifacts, self.settings, self.store = workspace, artifacts, settings, store
        self.conditions, self.models, self.workers, self.record = conditions, models, workers, record

    def conditions_for(self, worker, config):
        return {**self.conditions, 'worker': config, 'model': self.models[config['model_role']]}

    def material_id(self, path):
        if path not in self.workspace.paths():
            raise ValueError('part material is outside the current grant')
        if isinstance(self.workspace, ReferenceWorkspace) and path in self.workspace.references:
            return self.workspace.references[path]
        return 'sha256:' + hashlib.sha256(self.workspace.read(path)).hexdigest()

    def validate(self, part):
        if not part.reusable or part.worker not in self.settings.delegation.workers:
            raise ValueError('part requires separate review or an unavailable worker')
        config = self.workers(part.worker)
        if part.conditions != self.conditions_for(part.worker, config):
            raise ValueError('part requirements or execution conditions changed')
        for path, reference in part.grant.items():
            if self.material_id(path) != reference:
                raise ValueError('part source identity changed')
            # Check dependencies without claiming they were supplied to a model.
            self.artifacts.read(reference)
        return part

    def save(self, request, findings, grant, citations, reusable):
        config = self.workers(request.worker)
        part = OrganizationPart(request.task, request.context, request.worker,
            self.conditions_for(request.worker, config), dict(grant), findings, citations,
            {'scope_id': request.identity.scope_id, 'agent_id': request.identity.agent_id, 'run_id': request.identity.run_id}, reusable)
        reference = self.store.save(part)
        self.workspace.retained_parts[reference] = {'artifact_id': reference, 'disposition': 'new',
            'producer': part.producer, 'reusable': part.reusable}
        self.record('organization-part-saved', artifact_id=reference, producer=part.producer, reusable=part.reusable)
        return reference

    def tools(self):
        def result(value):
            return AgentToolResult([TextBlock(json.dumps(value, ensure_ascii=False))])
        async def catalog(ctx):
            cursor = ctx.args.get('cursor', 0)
            limit = ctx.args.get('limit', self.settings.catalog.default_entries)
            if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= self.settings.catalog.max_entries:
                raise ValueError('invalid retained-part directory page')
            rows, unavailable = [], 0
            if self.settings.retention.reuse:
                for reference in self.store.entries():
                    try:
                        part = self.validate(self.store.read(reference))
                    except (ValueError, KeyError, OSError, TypeError) as exc:
                        self.record('organization-part-unavailable', artifact_id=reference, error=type(exc).__name__, reason=str(exc)[:4000])
                        unavailable += 1
                        continue
                    rows.append({'part_id': reference, 'question': part.question[:self.settings.retention.preview_characters],
                        'worker': part.worker, 'source_count': len(part.findings['sources']),
                        'unknown_count': len(part.findings['unknowns'])})
            return result({'parts': rows[cursor:cursor+limit], 'total': len(rows), 'unavailable_count': unavailable,
                'next_cursor': cursor+limit if cursor+limit < len(rows) else None,
                'note': 'Historical child findings; read selected parts before using them.'})
        async def read(ctx):
            if not self.settings.retention.reuse:
                raise ValueError('retained part reuse is disabled')
            reference = ctx.args['part_id']; require_hash(reference)
            if reference not in self.store.entries():
                raise ValueError('unknown retained part')
            part = self.validate(self.store.read(reference))
            path = 'context/organization-parts/' + reference[7:] + '.json'
            if isinstance(self.workspace, ReferenceWorkspace):
                self.workspace.references[path] = reference
            else:
                data = canonical_json(part.to_dict()).encode()
                if sum(map(len, self.workspace.files.values())) + len(data) > self.workspace.max_bytes:
                    raise ValueError('retained part exceeds workspace allocation')
                self.workspace.files[path] = data
            page = WorkspaceEvidence(self.workspace, settings=self.settings).read(path,
                offset=ctx.args.get('offset', 0), limit=ctx.args.get('limit', self.settings.read.default_characters))
            if page.get('text'):
                for source in part.findings['sources']:
                    self.workspace.delegated_paths.setdefault(source['path'], set()).add(source['citation_id'])
                    for run in self.workspace.access.run_ids:
                        supplied_table = ''
                        if source['path'] in {'context/executions.json', 'context/evaluations.json'}:
                            span = part.citations[source['citation_id']]
                            supplied_table = self.artifacts.read(span['artifact_id']).decode('utf-8')[span['start']:span['end']]
                        if (source['path'].startswith('context/executions/' + run + '/')
                                or ('\"run_id\":\"' + run + '\"') in supplied_table):
                            self.workspace.access.delegated_supplied.add(run)
                self.workspace.retained_parts.setdefault(reference, {'artifact_id': reference, 'disposition': 'reused',
                    'producer': part.producer, 'reusable': part.reusable})
                self.record('organization-part-reused', artifact_id=reference, producer=part.producer,
                    scope='Historical child reading; current model received a derived part.')
            return result(page)
        return (
            AgentTool('catalog_parts', 'Browse retained parts', self.settings.instructions.catalog_parts,
                {'type': 'object', 'properties': {'cursor': {'type': 'integer'}, 'limit': {'type': 'integer'}}, 'additionalProperties': False}, catalog),
            AgentTool('read_part', 'Read retained part', self.settings.instructions.read_part,
                {'type': 'object', 'properties': {'part_id': {'type': 'string'}, 'offset': {'type': 'integer'},
                    'limit': {'type': 'integer'}}, 'required': ['part_id'], 'additionalProperties': False}, read))
