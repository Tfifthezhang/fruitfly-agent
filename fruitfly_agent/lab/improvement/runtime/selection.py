"""Offline method discovery and per-job binding; never change the active improver."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..api import MethodOption
from .host import HostedTextImprover
from fruitfly_agent.lab.algorithms.targets import TextTarget


@dataclass(frozen=True)
class BindingTemplate:
    """Borrowed runtime services, without an allocated search strategy."""
    config: Any
    workspace: Path
    target: TextTarget
    task_source: Any
    services_factory: Any
    parameters: dict = field(default_factory=dict)
    role_configs: dict = field(default_factory=dict)
    workflow: Any = None


@dataclass(frozen=True)
class MethodBinding:
    """Borrow runtime dependencies; bound hosts own only their per-job state."""
    template: HostedTextImprover | BindingTemplate
    target: TextTarget
    parameters: dict
    resources: list = field(default_factory=list)
    components: dict = field(default_factory=dict)

    def own(self, resource):
        if not any(item is resource for item in self.resources):
            self.resources.append(resource)
        return resource

    def text_host(self, strategy, *, label, confirm_on_holdout=False):
        template = self.template
        role_configs = dict(template.role_configs or {})
        for name, requested in self.parameters.items():
            if not name.endswith('_profile'):
                continue
            if requested and requested != template.parameters.get(name, ''):
                raise ValueError('select auxiliary models in configuration before starting a new session')
            if not requested:
                role_configs.pop(name.removesuffix('_profile'), None)
        host = HostedTextImprover(strategy, template.config, template.workspace, self.parameters,
            target=self.target, label=label, role_configs=role_configs,
            services_factory=template.services_factory,
            task_source=template.task_source.with_legacy(self.parameters['cases_path']),
            trial_targets=tuple(t for key, t in self.components.items()
                                if key.startswith('text-target:') and getattr(t, 'project_in_trials', False)),
            confirm_on_holdout=confirm_on_holdout)
        self.own(host)
        if (template.workflow is not None and self.target.snapshot().role == 'H'
                and self.target.snapshot().schema == 'text-v1'):
            from ..automatic.workflow import AutomaticWorkflow
            host.configure_workflow(AutomaticWorkflow(template.workflow.processor, template.workflow.policy))
        return host


class MethodSelection:
    """Only installed, supported bindings appear; missing capabilities stay explicit.

    The default text host remains usable for embeddings without method metadata.
    No strategy factory or Provider operation runs during discovery.
    """
    def __init__(self, definitions, default_id, default, targets, *, executable_roles=frozenset({'H'}),
                 enabled_ids=frozenset(), provided=frozenset(), components=None, configured=None,
                 preferences=None, save_preferences=None):
        self.definitions = {d.descriptor.mechanism_id: d for d in definitions
                            if d.improvement is not None or d.descriptor.mechanism_id == default_id}
        self.default_id, self.default = default_id, default
        self.targets = dict(targets)
        self.executable_roles = executable_roles
        self.bound = []
        self.owned_bindings = {}
        self.enabled_ids, self.provided = enabled_ids, provided
        self.components = dict(components or {})
        self.configured = dict(configured or {})
        self.preferences = dict(preferences or {})
        self.save_preferences = save_preferences

    def options(self, role, target_id):
        target = self.targets.get(target_id)
        snapshot = target.snapshot() if target is not None else None
        if snapshot is None or snapshot.role != role:
            return ()
        rows = []
        for identity, definition in self.definitions.items():
            support = definition.improvement
            if support is not None and (role not in support.roles or snapshot.schema not in support.schemas):
                continue
            if support is None and (identity != self.default_id or target_id != self.default_target()):
                continue
            reason = ''
            if role not in self.executable_roles and role not in getattr(target, 'adoption_roles', ()):
                reason = 'No executable comparison and adoption adapter is registered for this role.'
            elif self.default is None:
                reason = 'No search host is available in this runtime.'
            elif definition.descriptor.requires - self.enabled_ids:
                reason = 'Missing runtime mechanisms: ' + ', '.join(sorted(definition.descriptor.requires - self.enabled_ids))
            elif definition.requires_capabilities - self.provided:
                reason = 'Missing runtime capabilities: ' + ', '.join(sorted(definition.requires_capabilities - self.provided))
            elif definition.descriptor.conflicts & self.enabled_ids:
                reason = 'The method conflicts with an enabled runtime mechanism.'
            elif support is not None and not isinstance(self.default, (HostedTextImprover, BindingTemplate)):
                reason = 'This runtime host does not provide per-job method binding.'
            elif support is not None:
                missing = support.required_capabilities - self.default.services_factory.capabilities
                if missing:
                    reason = 'Missing execution capabilities: ' + ', '.join(sorted(missing))
            initial = (self.default.parameters if identity == self.default_id and isinstance(self.default, HostedTextImprover)
                       else self.configured.get(identity, {}))
            preferred = self.preferences.get(target_id, {})
            if preferred.get('method') == identity:
                initial = {**initial, **preferred['parameters']}
            parameters = tuple({**p.to_dict(), 'value': initial.get(p.name, p.default),
                                'group': 'budget' if support is not None and p.name in support.budget_parameters else
                                    'materials' if support is not None and p.name in support.material_parameters else 'parameters'}
                               for p in definition.descriptor.parameters)
            sources = ('saved',)
            if (not reason and role == 'H' and snapshot.binding.kind == 'prompt'
                    and isinstance(self.default, (HostedTextImprover, BindingTemplate))
                    and 'workflow-trials' in self.default.services_factory.capabilities):
                sources = ('saved', 'benchmark')
            rows.append(MethodOption(identity, definition.descriptor.label, definition.descriptor.description,
                not reason, reason, identity == self.preferences.get(target_id, {}).get('method', self.default_id),
                tuple((c.layer, c.family) for c in definition.descriptor.contributions), parameters, sources,
                support.usage.details if support is not None and support.usage is not None else (),
                support.direction_help if support is not None else 'Optional guidance for the configured search host.',
                definition.implementation_path, definition.documentation_path))
        return tuple(sorted(rows, key=lambda item: (not item.available, not item.default, item.method_id)))

    def default_target(self):
        if isinstance(self.default, (HostedTextImprover, BindingTemplate)):
            return self.default.target.snapshot().target_id
        return self.default.preview().target_id if self.default is not None else ''

    def select(self, *, method_id=None, target_id=None, parameters=None, experiment=False):
        identity = method_id or self.default_id
        target_id = target_id or self.default_target()
        target = self.targets.get(target_id)
        if target is None:
            raise ValueError('unknown improvement target')
        definition = self.definitions.get(identity)
        if definition is not None and definition.improvement is not None:
            snapshot = target.snapshot()
            if snapshot.role not in definition.improvement.roles or snapshot.schema not in definition.improvement.schemas:
                raise ValueError('The method does not support this target role or format.')
        option = next((item for item in self.options(target.snapshot().role, target_id)
                       if item.method_id == identity), None)
        if option is None or not option.available:
            raise ValueError(option.reason if option else 'unknown improvement method')
        if (identity == self.default_id and target_id == self.default_target() and not parameters
                and not experiment and target_id not in self.preferences
                and not isinstance(self.default, BindingTemplate)):
            return self.default
        definition = self.definitions[identity]
        if definition.improvement is None:
            raise ValueError('this method does not support per-job binding')
        initial = (self.default.parameters if identity == self.default_id and isinstance(self.default, HostedTextImprover)
                   else self.configured.get(identity, {}))
        preferred = self.preferences.get(target_id, {})
        if preferred.get('method') == identity:
            initial = {**initial, **preferred['parameters']}
        values = {**initial, **(parameters or {}), 'target': target_id}
        if definition.validate_parameters is not None:
            definition.validate_parameters(values)
        values = definition.descriptor.normalize_parameters(values)
        binding = MethodBinding(self.default, target, values, components=self.components)
        try:
            host = definition.improvement.bind(binding)
            binding.own(host)
            if experiment:
                if not isinstance(host, HostedTextImprover) or target.snapshot().role != 'H':
                    raise ValueError('original-task experiments require an H text search host')
                if host.workflow is None:
                    from ..automatic.workflow import AutomaticPolicy, AutomaticWorkflow
                    from ..failure_processing.processors import ReplayFailureProcessor
                    host.configure_workflow(AutomaticWorkflow(ReplayFailureProcessor(), AutomaticPolicy()))
            if isinstance(host, HostedTextImprover) and definition.improvement.usage is not None:
                host.method_usage = definition.improvement.usage
            from ..api import TextImprover
            if not isinstance(host, TextImprover):
                raise TypeError('method binding must provide the text host contract')
            self.owned_bindings[id(host)] = tuple(binding.resources)
            self.bound.extend(binding.resources)
            return host
        except BaseException:
            for resource in reversed(binding.resources):
                close = getattr(resource, 'close', None)
                if close is not None:
                    try:
                        close()
                    except Exception:
                        pass
            raise

    def close(self):
        errors = []
        for host in reversed(self.bound):
            close = getattr(host, 'close', None)
            if close is not None:
                try:
                    close()
                except BaseException as exc:
                    errors.append(exc)
        self.bound.clear()
        self.owned_bindings.clear()
        if errors:
            raise RuntimeError('improvement method cleanup failed') from errors[0]

    def lazy_default(self):
        return LazyImprover(self)

    def experiment_available(self):
        return (isinstance(self.default, (HostedTextImprover, BindingTemplate))
                and 'workflow-trials' in self.default.services_factory.capabilities
                and any(option.available for option in self.options('H', 'base_prompt')))

    def remember(self, host):
        if not isinstance(host, HostedTextImprover):
            return
        target_id = host.target.snapshot().target_id
        self.preferences[target_id] = {'method': host.spec.algorithm_id, 'parameters': dict(host.parameters)}
        if self.save_preferences is not None:
            self.save_preferences(self.preferences)

    def release(self, host):
        if host is self.default or isinstance(host, LazyImprover):
            return
        resources = self.owned_bindings.pop(id(host), ())
        for resource in reversed(resources):
            self.bound[:] = [item for item in self.bound if item is not resource]
            close = getattr(resource, 'close', None)
            if close is not None:
                close()


class LazyImprover:
    """Compatibility default for direct callers; allocate a method only on use."""
    def __init__(self, methods):
        self.methods = methods
        self.host = None

    def resolve(self):
        if self.host is None:
            self.host = self.methods.select(method_id=self.methods.default_id)
        return self.host

    def preview(self, *, task=None):
        return self.resolve().preview(task=task)

    async def search(self, *args, **kwargs):
        return await self.resolve().search(*args, **kwargs)

    def cancel(self):
        return self.host.cancel() if self.host is not None else False

    def progress(self):
        return self.host.progress() if self.host is not None else None

    def experiment_target_id(self):
        return self.methods.default_target()

    def experiment_available(self):
        return 'workflow-trials' in self.methods.default.services_factory.capabilities

    def improvement_identity(self):
        # Resolving a temporary job must not mutate the parent I identity.
        return {'methods': [{
            'id': identity, 'implementation': definition.implementation_id,
            'parameters': self.methods.configured.get(identity, {})}
            for identity, definition in sorted(self.methods.definitions.items())]}

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return getattr(self.resolve(), name)


def build_method_selection(catalog, selections, default, targets, *, components=None,
                           config=None, workspace=None, preferences=None, save_preferences=None):
    resolved = catalog.resolve(selections)
    identity = next((d.definition.descriptor.mechanism_id for d in resolved
                     if 'text-improver' in d.definition.provides
                     or d.definition.descriptor.exclusive_group == 'text-improver'), '')
    definitions = catalog.definitions()
    if default is None and config is not None and 'base_prompt' in targets:
        from ..tasks import TASK_PACK_COMPONENT
        from ..trials import TRIAL_SERVICES_COMPONENT
        from .services import NativeSearchServices
        default = BindingTemplate(config=config, workspace=workspace, parameters={},
            target=targets['base_prompt'], role_configs={}, workflow=None,
            services_factory=components.get(TRIAL_SERVICES_COMPONENT, NativeSearchServices),
            task_source=components[TASK_PACK_COMPONENT])
        identity = next((d.descriptor.mechanism_id for d in definitions
                         if d.improvement is not None and 'H' in d.improvement.roles
                         and 'text-v1' in d.improvement.schemas), '')
    # Method-owned targets are registered without enabling a search algorithm.
    target_capabilities = frozenset(capability for d in definitions
        if d.improvement is not None and d.improvement.prepare_targets is not None
        for capability in d.provides if capability != 'text-improver')
    return MethodSelection(definitions, identity, default, targets,
        enabled_ids=frozenset(item.definition.descriptor.mechanism_id for item in resolved),
        provided=frozenset(capability for item in resolved for capability in item.definition.provides) | target_capabilities,
        components=components, configured={s.mechanism_id: dict(s.parameters) for s in selections},
        preferences=preferences, save_preferences=save_preferences)
