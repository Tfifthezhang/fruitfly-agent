"""Offline harness inventory from owner declarations, without installers or clients."""
from dataclasses import asdict, dataclass
import hashlib
import json

from fruitfly_agent.runtime_spec import execution_values


@dataclass(frozen=True)
class ComponentSpec:
    component_id: str
    role: str = 'H'
    kind: str = 'instructions'
    schema: str = 'text-v1'
    required_capabilities: frozenset[str] = frozenset()

    def __post_init__(self):
        if self.role not in {'H', 'S', 'I'} or not self.component_id:
            raise ValueError('component declaration needs an ID and H/S/I role')


@dataclass(frozen=True)
class ResolvedHarness:
    profile_id: str
    mechanisms: tuple
    tools: tuple[str, ...]
    execution: dict
    components: tuple[ComponentSpec, ...]
    owners: tuple[tuple[str, str], ...]
    execution_owners: tuple[tuple[str, str], ...] = ()

    def to_dict(self):
        result = asdict(self)
        for component in result['components']:
            component['required_capabilities'] = sorted(component['required_capabilities'])
        return json.loads(json.dumps(result))

    @property
    def identity(self):
        return 'sha256:' + hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def select(self, component_ids, capabilities, roles):
        components = {c.component_id: c for c in self.components}
        for name in component_ids:
            if name not in components:
                raise ValueError('component is absent from the configured harness: ' + name)
            component = components[name]
            missing = component.required_capabilities - capabilities
            if component.role not in roles or missing:
                raise ValueError('execution backend cannot edit ' + name + '; missing capability or role: '
                    + ', '.join(sorted(missing or {component.role})))
        return tuple(components[name] for name in component_ids)


def resolve_harness(profile, catalog):
    resolved = catalog.resolve(profile.mechanisms)
    enabled = {item.definition.descriptor.mechanism_id: item for item in resolved}
    components, owners, tools, controlled = {}, {}, set(), {}
    for definition in catalog.definitions():
        name = definition.descriptor.mechanism_id
        active = enabled.get(name)
        if active:
            for tool in definition.descriptor.effects.tools:
                tools.add(tool)
                key = 'tool-guidance.' + tool
                if key in components:
                    raise ValueError('duplicate component declaration: ' + key)
                components[key] = ComponentSpec(key, kind='tool-guidance', required_capabilities=frozenset({'tool:' + tool}))
                owners[key] = name
            for field in definition.execution_fields:
                if field in controlled:
                    raise ValueError('multiple mechanisms control execution field: ' + field)
                controlled[field] = name
        if definition.component_specs is not None:
            parameters = active.parameters if active else {}
            for component in definition.component_specs(parameters, active is not None):
                if component.role == 'S' and active is None:
                    raise ValueError('inactive owner cannot declare editable state: ' + name)
                key = component.component_id
                if key in components:
                    raise ValueError('duplicate component declaration: ' + key)
                components[key], owners[key] = component, name
    mechanisms = tuple({'id': item.definition.descriptor.mechanism_id, 'parameters': dict(item.parameters),
        'implementation_id': item.definition.implementation_id} for item in resolved)
    return ResolvedHarness(profile.profile_id, mechanisms, tuple(sorted(tools)), execution_values(profile.execution),
        tuple(components[key] for key in sorted(components)), tuple(sorted(owners.items())), tuple(sorted(controlled.items())))


def verify_runtime(inventory, config, targets):
    """Compare declarative availability with assembled objects before task execution."""
    from dataclasses import replace
    from fruitfly_agent.runtime_spec import effective_execution
    actual = {target.snapshot().target_id: target for target in targets if target.snapshot().binding.kind != 'components'}
    expected = {component.component_id: component for component in inventory.components}
    if set(actual) != set(expected):
        raise ValueError('assembled component inventory differs from declarations: '
            + ', '.join(sorted(set(actual) ^ set(expected))))
    if set(t.name for t in config.tools) != set(inventory.tools):
        raise ValueError('assembled tools differ from enabled mechanism declarations')
    values = effective_execution(config)
    from fruitfly_agent.runtime_spec.execution import flatten_execution
    for name, value in flatten_execution(inventory.execution).items():
        if name not in dict(inventory.execution_owners) and flatten_execution(values)[name] != value:
            raise ValueError('mechanism changed an undeclared execution field: ' + name)
    components = []
    for key, spec in expected.items():
        target = actual[key]
        snapshot = target.snapshot()
        if snapshot.role != spec.role:
            raise ValueError('assembled component role differs from declaration: ' + key)
        components.append(replace(spec, schema=snapshot.schema))
    return replace(inventory, execution=values, components=tuple(components))
