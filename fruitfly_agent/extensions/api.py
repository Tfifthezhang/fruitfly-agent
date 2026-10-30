"""Collect declarations before publishing an extension into a host."""
from dataclasses import dataclass, field, replace
import inspect
import json
from types import MappingProxyType
from fruitfly_agent.improvement.contracts.versions import canonical_json

from fruitfly_agent.core.extensions.hooks import HookRegistry, HOOK_NAMES
from fruitfly_agent.core.extensions.operations import OperationSupervisor
from fruitfly_agent.lab.catalog import LabCatalog
from fruitfly_agent.lab.improvement.api import WorkflowBindings
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.lab.improvement.strategies import StrategyRegistry, builtin_strategies


class ExtensionContext:
    """One runtime or job scope. Retired contexts reject subsequent operations."""
    def __init__(self, identity, *, record=None, own=None):
        self.identity = identity
        self._record, self._own = record, own
        self._state = {}
        self._resources = []
        self._closed = False

    def check(self):
        if self._closed:
            raise RuntimeError('extension context is retired')

    @property
    def state(self):
        self.check()
        return self._state

    def record(self, value):
        self.check()
        if self._record is None:
            raise ValueError('extension record capability is unavailable')
        self._record(json.loads(canonical_json(value)))

    def own(self, resource):
        self.check()
        if self._own is None:
            raise ValueError('extension resource capability is unavailable')
        if all(value is not resource for value in self._resources):
            self._resources.append(resource)
        return resource

    def close(self):
        if self._closed:
            return None
        self._closed = True
        resources, self._resources = tuple(reversed(self._resources)), []
        async def retire():
            errors = []
            for resource in resources:
                callback = getattr(resource, 'aclose', None) or getattr(resource, 'close', None)
                if callback is None:
                    continue
                try:
                    await OperationSupervisor().run(callback, timeout=10)
                except BaseException as exc:
                    errors.append(exc)
            if errors:
                raise RuntimeError('extension resource cleanup failed') from errors[0]
        return retire() if resources else None

    async def aclose(self):
        value = self.close()
        if value is not None:
            await value


class ExtensionTrialSetup:
    def __init__(self, scopes, hooks):
        self.scopes, self.hooks = scopes, hooks

    async def aclose(self):
        errors = []
        for scope in reversed(self.scopes):
            try:
                await scope.aclose()
            except BaseException as exc:
                errors.append(exc)
        if errors:
            raise RuntimeError('trial extension cleanup failed') from errors[0]


def bind_agent_hooks(api, scope, hooks):
    for event, handler, timeout in api.agent_observers:
        async def observe(value, handler=handler, scope=scope):
            scope.check()
            result = handler(value, scope)
            return await result if inspect.isawaitable(result) else result
        hooks.on(event, observe, timeout=timeout)
    for event, handler, required, timeout in api.agent_interceptors:
        async def intercept(value, handler=handler, scope=scope):
            scope.check()
            result = handler(value, scope)
            return await result if inspect.isawaitable(result) else result
        hooks.add(event, intercept, required=required, timeout=timeout)


@dataclass
class ExtensionAPI:
    """Registration only. Runtime operations are supplied to callbacks later."""
    identity: str
    mechanisms: list = field(default_factory=list)
    generators: list = field(default_factory=list)
    strategies: list = field(default_factory=list)
    commands: dict = field(default_factory=dict)
    agent_observers: list = field(default_factory=list)
    improvement_observers: list = field(default_factory=list)
    agent_interceptors: list = field(default_factory=list)
    _sealed: bool = False

    def check(self):
        if self._sealed:
            raise RuntimeError('extension registration is closed')

    def register_mechanism(self, definition):
        self.check()
        self.mechanisms.append(definition)

    def register_generator(self, identity, factory, **metadata):
        self.check()
        self.generators.append((identity, factory, metadata))

    def register_strategy(self, definition):
        self.check()
        self.strategies.append(definition)

    def register_command(self, name, handler, *, summary=''):
        self.check()
        if name in self.commands or not callable(handler):
            raise ValueError('duplicate or invalid extension command')
        self.commands[name] = (handler, summary)

    def observe_agent(self, event, handler, *, timeout=10):
        self.check()
        if event not in HOOK_NAMES or not callable(handler):
            raise ValueError('invalid Agent observation')
        self.agent_observers.append((event, handler, timeout))

    def intercept_agent(self, event, handler, *, required=True, timeout=10):
        self.check()
        if event not in HOOK_NAMES or event == 'request_prepared' or not callable(handler) or type(required) is not bool:
            raise ValueError('invalid Agent interception')
        self.agent_interceptors.append((event, handler, required, timeout))

    def observe_improvement(self, event, handler):
        self.check()
        from fruitfly_agent.improvement.contracts.lifecycle import HOOK_NAMES as names
        if event not in names or not callable(handler):
            raise ValueError('invalid Improvement observation')
        self.improvement_observers.append((event, handler))


class ExtensionSet:
    """Frozen contributions; factories and state are never shared across jobs."""
    def __init__(self, registrations=(), *, identities=(), validate=lambda: None):
        self.registrations = tuple(registrations)
        self.identities = tuple(identities)
        self.validate = validate
        if len(self.identities) != len(self.registrations):
            raise ValueError('every extension requires a frozen implementation identity')
        commands = set()
        for api in self.registrations:
            if commands & api.commands.keys():
                raise ValueError('extension command collision')
            commands.update(api.commands)
            api.mechanisms, api.generators, api.strategies = tuple(api.mechanisms), tuple(api.generators), tuple(api.strategies)
            api.commands = MappingProxyType(dict(api.commands))
            api.agent_observers = tuple(api.agent_observers)
            api.agent_interceptors = tuple(api.agent_interceptors)
            api.improvement_observers = tuple(api.improvement_observers)
            api._sealed = True

    def catalog(self, base):
        self.validate()
        definitions = [definition for api in self.registrations for definition in api.mechanisms]
        result = base.extended(definitions)
        result.require_optimization()
        original = result.bootstrap
        def bootstrap(state, context):
            self.validate()
            state = original(state, context) if original else state
            hooks = state.config.hooks.clone() if state.config.hooks else HookRegistry()
            for api in self.registrations:
                scope = context.own(ExtensionContext(api.identity,
                    record=(lambda value, identity=api.identity: context.session.append('meta', {'kind': 'extension', 'extension': identity, 'data': value}))
                        if context.session is not None else None, own=context.own))
                state = state.with_component('extension:' + api.identity, scope)
                bind_agent_hooks(api, scope, hooks)
            return replace(state, config=replace(state.config, hooks=hooks))
        return LabCatalog(result.definitions(), bootstrap=bootstrap,
            extension_identities=(*base.extension_identities, *self.identities))

    def bindings(self, base=None):
        base = base or WorkflowBindings()
        generators = GeneratorRegistry()
        if base.generators is not None:
            for item in base.generators.definitions():
                generators.register(item.generator_id, base.generators.factories[item.generator_id],
                    implementation_id=item.implementation_id, label=item.label,
                    required_capabilities=item.required_capabilities, supports_task_sets=item.supports_task_sets)
        else:
            from fruitfly_agent.lab.improvement.editor.generators import AgentGenerator
            generators.register('agent-editor-v1', AgentGenerator)
        strategies = StrategyRegistry((base.strategies or builtin_strategies()).definitions())
        for api in self.registrations:
            for identity, factory, metadata in api.generators:
                generators.register(identity, factory, **metadata)
            for definition in api.strategies:
                strategies.register(definition)
        component_factory = base.components
        from fruitfly_agent.lab.improvement.components import component_registry
        def setup(services):
            self.validate()
            scopes, agent_hooks = [], HookRegistry()
            for api in self.registrations:
                scope = ExtensionContext(api.identity,
                    record=lambda value, identity=api.identity: services.record('extension', extension=identity, data=value),
                    own=services.own)
                scopes.append(scope)
                bind_agent_hooks(api, scope, agent_hooks)
            return ExtensionTrialSetup(scopes, agent_hooks)
        def components(targets):
            registry = (component_factory or component_registry)(targets)
            if any(api.agent_observers or api.agent_interceptors for api in self.registrations):
                registry.trial_setups = (*registry.trial_setups, setup)
            return registry
        previous = base.hooks
        def hooks(context):
            self.validate()
            if previous is not None:
                previous(context)
            for api in self.registrations:
                scope = context.services.own(ExtensionContext(api.identity,
                    record=lambda value, identity=api.identity: context.services.record('extension', extension=identity, data=value), own=context.services.own))
                for event, handler in api.improvement_observers:
                    async def observe(value, handler=handler, scope=scope):
                        scope.check()
                        result = handler(value, scope)
                        return await result if inspect.isawaitable(result) else result
                    context.services.hooks.on(event, observe)
        from fruitfly_agent.lab.improvement.workflow.mechanisms import extension_spec
        hooks.configuration = {'extensions': list(self.identities), 'host': extension_spec(previous)}
        return replace(base, generators=generators, strategies=strategies, hooks=hooks, components=components)

    def command_entries(self):
        return {name: entry for api in self.registrations for name, entry in api.commands.items()}

    def bind_commands(self, registry):
        registry.prepare_group('extensions', self.command_entries())()
