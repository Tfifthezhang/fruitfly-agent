"""Owned component adapters and validation."""
from ..contracts.components import ComponentDocument, ComponentFile, HarnessSnapshot


class ComponentRegistry:
    def __init__(self, adapters=()):
        self.adapters = {}
        self.options = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter):
        document = adapter.snapshot()
        if document.component_id in self.adapters:
            raise ValueError('duplicate component owner: ' + document.component_id)
        self.adapters[document.component_id] = adapter

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

