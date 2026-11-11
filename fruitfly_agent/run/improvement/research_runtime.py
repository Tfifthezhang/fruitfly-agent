"""Own persistent research role and assigned-evidence child runtime lifecycles."""
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
import inspect
from uuid import uuid4

from fruitfly_agent.core.context import ContextPipeline
from fruitfly_agent.core.session import Session
from fruitfly_agent.lab.catalog import PreparedAgentRuntime
from fruitfly_agent.lab.improvement.api import EvidenceDelegation, EvidenceSettings
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_agent.run.storage.research_bundles import ArtifactPort


class ResearchRuntimeFactory:
    def __init__(self, roles, role, directory, artifacts, settings, *, parts=None):
        self.roles, self.role, self.directory = roles, role, directory
        self.artifacts, self.settings = artifacts, EvidenceSettings.from_dict(settings)
        self.parts = parts if self.settings.retention.enabled else None
        if self.settings.retention.enabled and (parts is None or not self.settings.delegation.enabled):
            raise ValueError('incremental organization requires delegation and a durable part store')
        self.parameters = EvidenceDelegation.configuration(roles.profile, roles.catalog, self.settings.delegation.workers)
        worker_roles = {self.parameters['workers'][name]['model_role'] for name in self.settings.delegation.workers}
        for role_name in worker_roles:
            roles.specs[roles.alias(role_name)].require(streaming=True, tools=True)
        self.budget = None
        self.identity = {'implementation': 'assigned-evidence-runtime', 'role': role,
            'worker_models': {name: roles.identity(name) for name in sorted(worker_roles)}, 'parameters': self.parameters,
            'evidence': self.settings.to_dict(), 'implementation_id': self.parts.implementation_id if self.parts else None}

    @asynccontextmanager
    async def __call__(self, *, config, workspace, services, tools, system_prompt, prepare_config):
        if self.budget is None:
            self.budget = workspace.access.budget
        else:
            workspace.access.budget = self.budget
        token = uuid4().hex
        path = self.directory / (token + '.jsonl')
        parent = Session(path)
        port = ArtifactPort(self.artifacts)
        evidence_conditions = self.settings.to_dict()
        evidence_conditions.pop('delegation'); evidence_conditions.pop('retention')
        scope = EvidenceDelegation(workspace, port, self.settings,
            tools=self.parameters['evidence_tools'], record=services.record, workers=self.parameters['workers'],
            parts=self.parts, conditions={'role': self.role, 'mission_id': content_hash(system_prompt),
                'implementation_id': self.parts.implementation_id if self.parts else None,
                'evidence': evidence_conditions, 'parent_instructions': self.parameters['evidence_parent_instructions'],
                'child_instructions': self.parameters['evidence_child_instructions'],
                'execution': {k: self.parameters[k] for k in ('run_timeout_seconds', 'max_model_requests')}},
            models=self.identity['worker_models'])
        service = None
        async def prepare(request):
            session = Session(path.parent / (path.name + '.subagents') / request.identity.agent_id / 'session.jsonl')
            owned = []
            try:
                worker = scope.worker_config(request)
                child = prepare_config(self.roles.configuration(worker['model_role'], resources=owned), delegated=True)
                child_tools = scope.child_tools(request)
                child = replace(child, session=session, env=None, tools=child_tools, system_prompt='',
                    max_turns=None, max_tool_calls_per_turn=None)
                manifest = {'implementation': 'assigned-evidence-runtime', 'model_profile': self.roles.alias(worker['model_role']),
                    'model': child.model, 'max_tokens': child.max_tokens, 'context_window': child.context_window,
                    'tools': [{'name': t.name, 'parameters': t.parameters} for t in child_tools],
                    'permissions': {'read': 'assigned', 'write': 'deny', 'delegate': 'deny'},
                    'grant': scope.grants[request.identity.agent_id], 'worker': worker,
                    'configuration': self.identity, 'execution': {'session': 'independent', 'context': 'independent',
                        'effective_policy': service.detail(request.identity.agent_id, request.identity.run_id)['policy']}}
                manifest['identity'] = content_hash(canonical_json(manifest))
                session.append('meta', {'kind': 'child-runtime', 'identity': asdict(request.identity), 'manifest': manifest}, sync=True)
            except BaseException:
                await self._close(owned)
                session.close()
                raise
            async def start():
                services.check()
            async def close():
                await self._close(owned)
                session.close()
            return PreparedAgentRuntime(child, ContextPipeline(), manifest, start, close)
        try:
            service = scope.open_service(prepare, path.parent / (path.name + '.subagents'), self.artifacts, parent, self.parameters)
            parent_tools = (*tools, *scope.parent_tools(service, self.parameters))
            runtime_config = replace(config, session=parent, tools=parent_tools,
                system_prompt=system_prompt + '\n' + self.parameters['evidence_parent_instructions'],
                max_turns=None, max_tool_calls_per_turn=None)
            manifest = {**self.identity, 'session_id': token, 'tools': [t.name for t in parent_tools]}
            parent.append('meta', {'kind': 'research-runtime', 'manifest': manifest}, sync=True)
            services.record('research-runtime', session=str(path), identity=content_hash(canonical_json(manifest)))
            async def start():
                services.check()
            async def close():
                await service.close()
            runtime = PreparedAgentRuntime(runtime_config, ContextPipeline(), manifest, start, close, service.run_loop)
            await runtime.start()
            yield runtime
        finally:
            if service is not None:
                await service.close()
            parent.close()

    @staticmethod
    async def _close(resources):
        # Child Providers are independently owned; parent role Providers are borrowed.
        while resources:
            resource = resources[-1]
            close = getattr(resource, 'aclose', None) or getattr(resource, 'close', None)
            if close is not None:
                result = close()
                if inspect.isawaitable(result):
                    await result
            resources.pop()
