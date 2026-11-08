"""Construct only a requested research model role; no task environment starts."""
from dataclasses import asdict
from pathlib import Path
import os
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.lab.catalog import builtin_catalog, load_system_config
from fruitfly_agent.lab.catalog import RoleProvider
from fruitfly_agent.providers.registry import default_registry, load_model_specs
from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.workspace import WorkspacePaths
from fruitfly_agent.run.configuration.resolution import model_catalog_path
from fruitfly_agent.improvement.contracts.versions import content_hash, canonical_json


class ResearchRoles:
    def __init__(self, workspace, config_path, *, profile=None, registry=None, environment=None, overrides=None):
        self.workspace, self.config_path = Path(workspace).resolve(), Path(config_path).resolve()
        self.catalog = builtin_catalog()
        from fruitfly_agent.run.extensions import configured_extensions
        extensions = configured_extensions(self.config_path, profile_id=profile)
        self.extensions = extensions
        if extensions.registrations:
            self.catalog = extensions.catalog(self.catalog)
        self.profile = load_system_config(self.config_path, catalog=self.catalog).select(profile)
        self.model_path = model_catalog_path(self.profile, self.config_path)
        self.specs = load_model_specs(self.model_path)
        self.registry = registry or default_registry()
        self.environment = {**load_env(WorkspacePaths(self.workspace).secret_file()),
            **(dict(os.environ) if environment is None else environment)}
        self.providers = []
        self.overrides = dict(overrides or {})

    def alias(self, role):
        selected = self.overrides.get(role, self.profile.model_roles.get(role))
        if isinstance(selected, str):
            if selected not in self.specs:
                raise ValueError('unknown research model alias: ' + selected)
            return selected
        executor = self.overrides.get('executor', self.profile.model_profile)
        if not executor:
            if len(self.specs) != 1:
                raise ValueError('select the executor alias for inherited research roles')
            executor = next(iter(self.specs))
        alias = self.overrides.get(role, self.profile.resolved_model_roles(executor).get(role, executor))
        if alias not in self.specs:
            raise ValueError('unknown research model alias: ' + alias)
        return alias

    def configuration(self, role):
        alias = self.alias(role)
        spec = self.specs[alias]
        spec.require(streaming=True, tools=True)
        provider = None
        def binding():
            nonlocal provider
            if provider is None:
                actual = self.registry.create(spec, self.environment)
                self.providers.append(actual)
                provider = RoleProvider(actual, 'component-improvement', role)
            return provider
        class DeferredProvider:
            def __call__(self, view, *, signal=None):
                return binding()(view, signal=signal)
            def __getattr__(self, name):
                return getattr(binding(), name)
        return AgentLoopConfig(provider=DeferredProvider(),
            model=spec.model, max_tokens=spec.max_output_tokens, context_window=spec.context_window)

    def identity(self, role):
        alias = self.alias(role)
        return content_hash(canonical_json(asdict(self.specs[alias])))

    async def aclose(self):
        import inspect
        for provider in reversed(self.providers):
            close = getattr(provider, 'aclose', None) or getattr(provider, 'close', None)
            if close:
                result = close()
                if inspect.isawaitable(result):
                    await result
        self.providers.clear()
