"""Read-only, immutable child grants with separately attributed source receipts."""
from dataclasses import asdict
import hashlib
import json

from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.improvement.contracts.components import ComponentDocument, HarnessSnapshot
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.lab.agents.subagent.service import SubagentError, SubagentService
from fruitfly_agent.lab.agents.subagent.storage import SubagentStore
from fruitfly_agent.lab.agents.subagent.tools import create_tools
from fruitfly_agent.lab.agents.subagent.configuration import ProtocolSettings, ResultSettings
from .access import EvidenceAccess
from fruitfly_agent.lab.agents.subagent.workers import worker_definitions
from fruitfly_agent.lab.agents.subagent.contracts import ChildExecutionPolicy
from .resources import ReferenceWorkspace
from .tools import evidence_tools
from .parts import OrganizationPartCache


class EvidenceDelegation:
    """Lab owns material/citation policy; the host owns Sessions and Providers."""
    def __init__(self, workspace, artifacts, settings, *, tools, record, workers=None, parts=None, conditions=None, models=None):
        self.workspace, self.artifacts, self.settings = workspace, artifacts, settings
        if len(set(tools)) != len(tools) or set(tools) - {'catalog', 'search', 'read'}:
            raise ValueError('unsupported delegated evidence tools')
        self.tools, self.record = tuple(tools), record
        self.workers = worker_definitions({'workers': workers} if workers is not None else {})
        if set(settings.delegation.workers) - set(self.workers):
            raise ValueError('stage selects an unknown worker')
        self.scopes, self.grants, self.accepted = {}, {}, {}
        self.spans = {}
        self.service = None
        self.blocks = {}
        self.partial_parts = {}
        self.block_sizes = {}
        self.cache = OrganizationPartCache(workspace, artifacts, settings, parts,
            conditions=conditions or {}, models=models or {}, workers=self.worker_by_name, record=record) if parts is not None else None

    @staticmethod
    def configuration(profile, catalog, workers=()):
        selected = next((s for s in profile.mechanisms if s.mechanism_id == 'subagent' and s.enabled), None)
        if selected is None:
            raise ValueError('research delegation requires the enabled subagent component')
        definition = catalog.get('subagent')
        parameters = definition.descriptor.normalize_parameters(selected.parameters)
        definition.validate_parameters(parameters)
        declared = worker_definitions(parameters)
        if set(workers) - set(declared):
            raise ValueError('stage selects an unknown worker')
        roles = {'executor', *(role for definition in catalog.definitions() for role in definition.model_role_parameters)}
        if any(declared[name].model_role not in roles for name in workers):
            raise ValueError('worker references an undeclared model role')
        return parameters

    def open_service(self, prepare, root, artifacts, session, parameters):
        store = SubagentStore(root, artifacts, index=session)
        try:
            self.service = SubagentService(prepare, store,
                **{k: parameters[k] for k in ('max_concurrent', 'max_agents', 'run_timeout_seconds', 'max_model_requests', 'retirement_timeout')},
                instructions=parameters['evidence_child_instructions'],
                protocol=ProtocolSettings.from_parameters(parameters),
                results=ResultSettings.from_parameters(parameters), admit=self.admit, finalize=self.finalize, policy=self.execution_policy)
            return self.service
        except BaseException:
            store.close()
            raise

    def parent_tools(self, service, parameters):
        return (*create_tools(service, parameters, workers={name: self.workers[name].description for name in self.settings.delegation.workers}),
            *(self.cache.tools() if self.cache is not None else ()))

    def worker_by_name(self, name):
        config = self.workers[name].to_dict()
        config['capabilities']['tools'] = [name for name in config['capabilities']['tools'] if name in self.tools]
        return config

    def worker_config(self, request):
        return self.worker_by_name(request.worker)

    def execution_policy(self, request):
        worker = self.workers[request.worker]
        return ChildExecutionPolicy(worker.limits['seconds'], worker.limits['model_requests'], worker.instructions)

    def admit(self, request):
        if (request.worker not in self.settings.delegation.workers or not request.materials
                or set(request.materials) - set(self.workspace.paths())):
            raise SubagentError('invalid_material_grant')
        key = request.identity.agent_id
        if key in self.scopes:
            if tuple(request.materials) != tuple(self.grants[key]):
                raise SubagentError('material_grant_changed')
            return
        files, references, identities = {}, {}, {}
        for path in request.materials:
            if isinstance(self.workspace, ReferenceWorkspace) and path in self.workspace.references:
                reference = self.workspace.references[path]
                references[path] = reference
            else:
                data = self.workspace.read(path)
                files[path] = data
                reference = self.artifacts.put(data)
            identities[path] = reference
        self.spans[key] = {}
        def record(event, **fields):
            if event == 'evidence-page':
                self.spans[key][fields['citation_id']] = {name: fields[name] for name in ('path', 'artifact_id', 'start', 'end')}
                self.spans[key][fields['citation_id']]['kind'] = 'text'
            elif event == 'evidence-image':
                self.spans[key][fields['artifact_id']] = {'path': fields['path'], 'artifact_id': fields['artifact_id'], 'kind': 'image'}
            self.record('delegated-' + event, agent_id=key, **fields)
        placeholder = HarnessSnapshot((ComponentDocument('evidence-scope', 'evidence', 'H', 'assigned-evidence', ()),))
        worker = self.workers[request.worker]
        access = EvidenceAccess(self.workspace.access.run_ids, record=record, budget=self.workspace.access.budget,
            limits={'characters': worker.limits['evidence_characters'], 'responses': worker.limits['evidence_responses']})
        scope = ReferenceWorkspace(artifacts=self.artifacts, references=references,
            baseline=placeholder, files=files, writable_ids=(), access=access, record=record,
            max_bytes=self.workspace.max_bytes)
        self.scopes[key], self.grants[key] = scope, identities
        self.record('delegation-granted', agent_id=key, child_run_id=request.identity.run_id,
            materials=identities, permissions={'read': 'assigned', 'write': 'deny', 'delegate': 'deny'})

    def child_tools(self, request):
        scope = self.scopes[request.identity.agent_id]
        agent_id = request.identity.agent_id
        run_id = request.identity.run_id
        worker = self.worker_config(request)
        maximum = min(self.settings.read.max_characters, worker['result']['max_characters'])
        from .findings import validate_findings_block
        def validate(value):
            return validate_findings_block(value, scope, maximum)
        async def save(ctx):
            value = validate(ctx.args)
            size = len(canonical_json(value))
            if self.block_sizes.get(run_id, 0) + size > self.settings.findings.max_characters:
                raise ValueError('detailed findings cumulative character allowance exhausted')
            reference = self.artifacts.put(canonical_json(value).encode())
            blocks = self.blocks.setdefault(run_id, [])
            path = f'context/findings/{run_id}/partial-{len(blocks)}.json'
            partial = self.artifacts.put(canonical_json({
                'status': 'partial', 'identity': asdict(request.identity),
                'question': request.task, 'worker': request.worker, 'grant': self.grants[agent_id],
                'source_spans': [{**self.spans[agent_id][item['citation_id']], 'path': item['path']}
                                 for item in value['sources']],
                'artifact_id': reference, 'findings': value,
            }).encode())
            if isinstance(self.workspace, ReferenceWorkspace):
                self.workspace.references[path] = partial
            else:
                self.workspace.files[path] = self.artifacts.read(partial)
            blocks.append((reference, value))
            parts = self.partial_parts.setdefault(run_id, [])
            parts.append({'path': path, 'artifact_id': partial})
            index_path = f'context/findings/{run_id}/partial-index.json'
            index = self.artifacts.put(canonical_json({'status': 'partial', 'identity': asdict(request.identity),
                                                        'blocks': parts}).encode())
            if isinstance(self.workspace, ReferenceWorkspace):
                self.workspace.references[index_path] = index
            else:
                self.workspace.files[index_path] = self.artifacts.read(index)
            if self.service is not None:
                self.service.observe_partial(request.identity, reference=index, path=index_path, count=len(parts))
            if self.cache is not None:
                self._save_part(request, value, self.cache, partial=True)
            self.block_sizes[run_id] = self.block_sizes.get(run_id, 0) + size
            self.record('delegation-findings-block', child_run_id=run_id, artifact_id=reference,
                        partial_artifact_id=partial, path=path, index_artifact_id=index)
            return AgentToolResult([TextBlock(canonical_json({'artifact_id': reference, 'characters': size, 'partial_path': path,
                'remaining_characters': self.settings.findings.max_characters - self.block_sizes[run_id]}))])
        async def submit(ctx):
            value = validate(ctx.args)
            blocks = self.blocks.get(run_id, [])
            if blocks:
                if len(value['summary']) > self.settings.findings.summary_characters:
                    raise ValueError(f'final summary exceeds {self.settings.findings.summary_characters} characters; retain detail with save_findings')
                sources = {(v['path'], v['citation_id']): v for v in value['sources']}
                for _, block in blocks:
                    sources.update({(v['path'], v['citation_id']): v for v in block['sources']})
                value = {**value, 'sources': list(sources.values()), 'blocks': [ref for ref, _ in blocks]}
            if self.cache is not None:
                self._save_part(request, value, self.cache)
            self.accepted[run_id] = value
            return AgentToolResult([TextBlock('Attributed findings retained.')], terminate=True)
        text = {'type': 'string'}
        source = {'type': 'object', 'properties': {'path': text, 'citation_id': text},
            'required': ['path', 'citation_id'], 'additionalProperties': False}
        submission = AgentTool(name='submit_findings', label='Submit evidence findings',
            description=self.settings.instructions.submit_findings,
            parameters={'type': 'object', 'properties': {'summary': text,
                'sources': {'type': 'array', 'items': source}, 'unknowns': {'type': 'array', 'items': text}},
                'required': ['summary', 'sources', 'unknowns'], 'additionalProperties': False},
            execute=submit, requires_exclusive_batch=True)
        block_tool = AgentTool(name='save_findings', label='Save detailed findings',
            description=self.settings.instructions.save_findings,
            parameters=submission.parameters, execute=save)
        return (*tuple(t for t in evidence_tools(scope, settings=self.settings) if t.name in worker['capabilities']['tools']), block_tool, submission)

    def _save_part(self, request, value, cache: OrganizationPartCache, *, partial=False):
        if self.service is None:
            raise ValueError('retention requires a managed child lifecycle')
        row = self.service.detail(request.identity.agent_id, request.identity.run_id)
        citations = {source['citation_id']: self.spans[request.identity.agent_id][source['citation_id']] for source in value['sources']}
        cache.save(request, value, self.grants[request.identity.agent_id], citations,
            reusable=not row['steered'] and not row['continuation'], partial=partial)

    def finalize(self, request, result, summary):
        value = self.accepted.get(request.identity.run_id)
        if value is None:
            raise ValueError('evidence child did not submit validated findings')
        scope = self.scopes[request.identity.agent_id]
        block_paths = []
        for index, reference in enumerate(value.get('blocks', ())):
            path = 'context/findings/' + request.identity.run_id + '/' + str(index) + '.json'
            if isinstance(self.workspace, ReferenceWorkspace):
                self.workspace.references[path] = reference
            else:
                self.workspace.files[path] = self.artifacts.read(reference)
            block_paths.append(path)
        payload = {'block_paths': block_paths, 'identity': asdict(request.identity), 'worker': request.worker,
            'grant': self.grants[request.identity.agent_id], 'findings': value,
            'reading_scope': 'Child source reading; parent received derived findings, not original bytes.'}
        reference = self.artifacts.put(canonical_json(payload).encode())
        final_path = 'context/findings/' + request.identity.run_id + '/final.json'
        if isinstance(self.workspace, ReferenceWorkspace):
            self.workspace.references[final_path] = reference
        else:
            self.workspace.files[final_path] = canonical_json(payload).encode()
        self.record('delegation-findings', agent_id=request.identity.agent_id,
            child_run_id=request.identity.run_id, artifact_id=reference, sources=value['sources'])
        for source in value['sources']:
            self.workspace.delegated_paths.setdefault(source['path'], set()).add(source['citation_id'])
            span = getattr(scope, 'source_spans', {}).get((source['path'], source['citation_id']))
            if span is not None:
                from .provenance import retain_span
                retain_span(self.workspace, span['path'], span['artifact_id'], span['start'], span['end'])
        if value['sources']:
            self.workspace.access.delegated_supplied.update(scope.access.supplied)
        return canonical_json({'identity': payload['identity'], 'worker': request.worker,
            'summary': value['summary'][:self.settings.findings.summary_characters],
            'source_count': len(value['sources']), 'artifact_id': reference,
            'findings_path': final_path, 'block_paths': block_paths,
            'reading_scope': payload['reading_scope']})
