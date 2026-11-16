"""Own persistent research role and assigned-evidence child runtime lifecycles."""
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
import inspect
from uuid import uuid4

from fruitfly_agent.run.runtime.role_runtime import build_role_runtime
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
        self.parameters = EvidenceDelegation.configuration(roles.profile, roles.catalog, self.settings.delegation.workers) if self.settings.delegation.enabled else {}
        worker_roles = {self.parameters['workers'][name]['model_role'] for name in self.settings.delegation.workers} if self.parameters else set()
        for role_name in worker_roles:
            roles.specs[roles.alias(role_name)].require(streaming=True, tools=True)
        from fruitfly_agent.run.storage.work_products import WorkProductStore
        self.products = WorkProductStore(self.directory / "shared.work", artifacts)
        self.budget = None
        from fruitfly_agent.runtime_spec import execution_values
        from fruitfly_agent.lab.catalog import role_alias
        context_roles = []
        for selection in roles.profile.mechanisms:
            definition = roles.catalog.get(selection.mechanism_id)
            if selection.enabled and definition.role_safe:
                values = definition.descriptor.normalize_parameters(selection.parameters)
                context_roles.extend((definition.descriptor.mechanism_id + '.' + name, name, requirement, values)
                    for name, requirement in definition.model_role_parameters.items() if requirement.required_when(values))
        context_models = {}
        for runtime_role in {role, *worker_roles}:
            projected = replace(roles.profile, model_profile=roles.alias(runtime_role),
                model_roles={**roles.profile.model_roles, 'executor': roles.alias(runtime_role)})
            bindings = projected.resolved_model_roles(roles.alias(runtime_role))
            context_models[runtime_role] = {key: content_hash(canonical_json(asdict(
                roles.specs[role_alias(name, requirement, values, bindings)])))
                for key, name, requirement, values in context_roles}
        self.identity = {'implementation': 'assigned-evidence-runtime', 'role': role,
            'worker_models': {name: roles.identity(name) for name in sorted(worker_roles)}, 'parameters': self.parameters,
            'context_profile': content_hash(canonical_json({'components': [asdict(s) for s in roles.profile.mechanisms if roles.catalog.get(s.mechanism_id).role_safe],
                'execution': execution_values(roles.profile.execution), 'models': context_models})),
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
        products = self.products
        service = None
        def published(row):
            services.record('work-product-saved', **row)
            if service is not None:
                service.observe_product(row)
        products.on_publish = published
        parent_owned = []
        def assemble(config, session, tools, owned, role=None):
            return build_role_runtime(config, profile=self.roles.profile, catalog=self.roles.catalog,
                session=session, workspace=self.roles.workspace, tools=tools, owned=owned,
                provider_resolver=lambda alias, maximum: self.roles.provider_binding(alias, maximum, resources=owned),
                page_characters=self.settings.read.max_characters,
                work_products=products if session is parent else products.writer(session.path.parent.name),
                model_alias=self.roles.alias(role or self.role), artifacts=self.artifacts)
        if not self.parameters:
            try:
                runtime_config, pipeline, inventory = assemble(replace(config, system_prompt=system_prompt), parent, tools, parent_owned)
                manifest = {**self.identity, **inventory, "session_id": token, 'model': runtime_config.model, 'context_window': runtime_config.context_window, 'max_tokens': runtime_config.max_tokens, 'tools': [t.name for t in runtime_config.tools]}
                parent.append("meta", {"kind": "research-runtime", "manifest": manifest}, sync=True)
                async def start():
                    services.check()
                    await self._start(parent_owned)
                async def close():
                    pass
                runtime = PreparedAgentRuntime(runtime_config, pipeline, manifest, start, close, work_products=products)
                await runtime.start()
                yield runtime
            finally:
                await self._close(parent_owned)
                parent.close()
            return
        evidence_conditions = self.settings.to_dict()
        evidence_conditions.pop('delegation'); evidence_conditions.pop('retention')
        scope = EvidenceDelegation(workspace, port, self.settings,
            tools=self.parameters['evidence_tools'], record=services.record, workers=self.parameters['workers'],
            parts=self.parts, conditions={'role': self.role, 'mission_id': content_hash(system_prompt),
                'implementation_id': self.parts.implementation_id if self.parts else None,
                'context_profile': self.identity['context_profile'],
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
                child = replace(child, session=session, env=None, tools=child_tools, system_prompt='')
                child, pipeline, inventory = assemble(child, session, child_tools, owned, worker['model_role'])
                manifest = {**inventory, 'implementation': 'assigned-evidence-runtime', 'model_profile': self.roles.alias(worker['model_role']),
                    'model': child.model, 'max_tokens': child.max_tokens, 'context_window': child.context_window,
                    'tools': [{'name': t.name, 'parameters': t.parameters} for t in child.tools],
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
                await self._start(owned)
            async def close():
                await self._close(owned)
                session.close()
            return PreparedAgentRuntime(child, pipeline, manifest, start, close, work_products=products.writer(session.path.parent.name))
        try:
            service = scope.open_service(prepare, path.parent / (path.name + '.subagents'), self.artifacts, parent, self.parameters)
            parent_tools = (*tools, *scope.parent_tools(service, self.parameters))
            runtime_config = replace(config, session=parent, tools=parent_tools,
                system_prompt=system_prompt + '\n' + self.parameters['evidence_parent_instructions'])
            runtime_config, pipeline, inventory = assemble(runtime_config, parent, parent_tools, parent_owned)
            manifest = {**self.identity, **inventory, 'session_id': token, 'tools': [t.name for t in runtime_config.tools]}
            parent.append('meta', {'kind': 'research-runtime', 'manifest': manifest}, sync=True)
            services.record('research-runtime', session=str(path), identity=content_hash(canonical_json(manifest)))
            async def start():
                services.check()
                await self._start(parent_owned)
            async def close():
                await service.close()
            runtime = PreparedAgentRuntime(runtime_config, pipeline, manifest, start, close, service.run_loop, products)
            await runtime.start()
            yield runtime
        finally:
            if service is not None:
                await service.close()
            await self._close(parent_owned)
            parent.close()

    @staticmethod
    async def _start(resources):
        for resource in resources:
            start = getattr(resource, 'start', None)
            if callable(start):
                result = start()
                if inspect.isawaitable(result):
                    await result

    @staticmethod
    async def _close(resources):
        # Child Providers are independently owned; parent role Providers are borrowed.
        failures = []
        for resource in reversed(tuple(resources)):
            try:
                close = getattr(resource, 'aclose', None) or getattr(resource, 'close', None)
                if close is not None:
                    result = close()
                    if inspect.isawaitable(result):
                        await result
            except BaseException as exc:
                failures.append(exc)
            else:
                resources[:] = [item for item in resources if item is not resource]
        if failures:
            raise failures[0]
