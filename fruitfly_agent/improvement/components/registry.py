"""Owned component adapters and validation."""
from fruitfly_agent.improvement.contracts.components import ComponentDocument, ComponentFile, HarnessSnapshot


from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec


class ComponentRegistry:
    def __init__(self, adapters=()):
        self.adapters = {}
        self.options = {}
        self.trial_setups = ()
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter):
        document = adapter.snapshot()
        spec = getattr(adapter, 'optimization', None)
        if not isinstance(spec, OptimizationSpec) or spec.role != document.role:
            raise ValueError('component needs an owner-matching optimization declaration')
        if document.component_id in self.adapters:
            raise ValueError('duplicate component owner: ' + document.component_id)
        self.adapters[document.component_id] = adapter

    def admit(self, component_ids, capabilities, *, boundaries=frozenset({'task'}), updates=frozenset({'offline'})):
        if self.trial_setups and 'execution-setup' not in capabilities:
            raise ValueError('runner cannot initialize declared trial mechanisms')
        for name in component_ids:
            if name not in self.adapters:
                raise ValueError('unregistered optimization component: ' + name)
            adapter = self.adapters[name]
            adapter.optimization.admit(role=adapter.snapshot().role, capabilities=capabilities,
                boundaries=boundaries, updates=updates)

    def configure(self, options):
        if not isinstance(options, dict) or set(options) - set(self.adapters):
            raise ValueError('component options cite unavailable components')
        self.options = dict(options)
        for name, value in self.options.items():
            validate = getattr(self.adapters[name], 'validate_options', None)
            if validate is None:
                raise ValueError('component does not declare editable options: ' + name)
            validate(value)

    def snapshot(self):
        return HarnessSnapshot(tuple(a.snapshot() for a in self.adapters.values()))

    def descriptions(self, component_ids, *, snapshot=None):
        result = {}
        for name in component_ids:
            adapter = self.adapters[name]
            describe = getattr(adapter, 'describe_fields', None)
            if describe is None:
                raise ValueError('component must describe editable fields: ' + name)
            fields = tuple(describe(snapshot.component(name)) if snapshot is not None else describe())
            if not fields or len({f.path for f in fields}) != len(fields):
                raise ValueError('component must describe distinct editable fields: ' + name)
            result[name] = {'role': adapter.snapshot().role,
                            'fields': [f.to_dict() for f in fields],
                            'grant': self.options.get(name, {})}
        return result

    def validate(self, snapshot):
        if {c.component_id for c in snapshot.components} != set(self.adapters):
            raise ValueError('harness must preserve its registered component set')
        for document in snapshot.components:
            adapter = self.adapters[document.component_id]
            old = adapter.snapshot()
            if (old.role, old.kind, old.schema) != (document.role, document.kind, document.schema):
                raise ValueError('component ownership cannot change')
            adapter.validate(document)
            if document.component_id in self.options:
                adapter.validate_change(document, self.options[document.component_id])

    def export(self, snapshot, *, changed_only=True):
        self.validate(snapshot)
        values = []
        for document in snapshot.components:
            adapter = self.adapters[document.component_id]
            if changed_only and document == adapter.snapshot():
                continue
            export = getattr(adapter, 'export', None)
            if export is None:
                raise ValueError('component has no executable publication adapter: ' + document.component_id)
            values.append(export(document))
        if len({(v.kind, v.key) for v in values}) != len(values):
            raise ValueError('component publication bindings conflict')
        return tuple(values)

