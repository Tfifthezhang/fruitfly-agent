"""Construct independent nested runtimes through the shared runtime assembler."""
from dataclasses import replace
from typing import Any, cast
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.extensions.operations import OperationCleanupError
from fruitfly_agent.interactive.contracts.runtime import RuntimeCleanupError
from fruitfly_agent.interactive.application.runtime import RuntimeHandle
from fruitfly_agent.lab.catalog import PreparedAgentRuntime, RoleProvider, AgentRuntimeError

class ChildRuntimeFactory:
    def __init__(self, *, build, profile, config_path, catalog, environment, cwd,
                 provider_registry, artifacts, permission_policy, model_specs, authorization, parent_path):
        self.build, self.profile = build, profile
        self.config_path, self.catalog, self.environment = config_path, catalog, environment
        self.cwd, self.registry, self.artifacts = cwd, provider_registry, artifacts
        self.policy, self.models = permission_policy, model_specs
        self.authorization, self.parent_path = authorization, parent_path
        self.quarantined: list[Any] = []

    async def __call__(self, identity, model_alias, excluded):
        # Exclusion is supplied by the owning component, never model arguments.
        selections = tuple(s for s in self.profile.mechanisms if s.mechanism_id not in excluded)
        if any(item.definition.tool_provider is not None for item in self.catalog.resolve(selections)):
            raise AgentRuntimeError('unsupported_child_transports')
        profile = replace(self.profile, mechanisms=selections,
            component_documents=tuple(d for d in self.profile.component_documents if d.id not in excluded),
            model_profile=model_alias, model_roles={**self.profile.model_roles, 'executor': model_alias}, configured=True)
        path = self.parent_path.parent / (self.parent_path.name + '.subagents') / identity.agent_id / 'session.jsonl'
        session = Session(path)
        resources: list[Any] = []
        owner = RuntimeHandle(session=cast(Any, None), manifest={}, components={})
        try:
            runtime = self.build(profile, config_path=self.config_path, catalog=self.catalog,
                environment=self.environment, session=session, cwd=self.cwd, provider_registry=self.registry,
                resource_sink=resources, artifact_store=self.artifacts, permission_policy=replace(self.policy,
                    readonly_paths=(*self.policy.readonly_paths, self.parent_path, self.parent_path.parent / (self.parent_path.name + '.subagents'))),
                model_specs=self.models, shared_authorization=self.authorization)
            owner.components = {key: value for key, value in runtime.components.items() if value is not self.authorization}
            manifest = runtime.manifest.to_dict()
            session.append('meta', {'kind': 'child-runtime', 'identity': {
                'scope_id': identity.scope_id, 'agent_id': identity.agent_id, 'run_id': identity.run_id},
                'manifest': manifest}, sync=True)
            cleanup_failed = False
            async def start():
                nonlocal cleanup_failed
                try:
                    await owner.start()
                except RuntimeCleanupError as exc:
                    cleanup_failed = True
                    self.quarantined.append((owner, session))
                    raise OperationCleanupError('child startup cleanup was not confirmed') from exc
            async def close():
                nonlocal cleanup_failed
                if cleanup_failed:
                    raise OperationCleanupError('child retirement previously failed')
                try:
                    await owner.close()
                except RuntimeCleanupError as exc:
                    cleanup_failed = True
                    self.quarantined.append((owner, session))
                    raise OperationCleanupError('child resource retirement was not confirmed') from exc
                finally:
                    if not cleanup_failed:
                        session.close()
            return PreparedAgentRuntime(replace(runtime.config,
                provider=RoleProvider(runtime.config.provider, 'child-execution', 'subagent')),
                runtime.context_pipeline, manifest, start, close)
        except BaseException:
            owner.components = {str(i): r for i, r in enumerate(resources) if r is not self.authorization}
            try:
                await owner.close()
            except RuntimeCleanupError as exc:
                self.quarantined.append((owner, session))
                raise OperationCleanupError('partial child construction cleanup was not confirmed') from exc
            else:
                session.close()
            raise
