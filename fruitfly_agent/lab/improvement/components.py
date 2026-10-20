"""Component registry and bridges to existing object-owned text adapters."""

from .contracts.pipeline import ComponentDocument, ComponentFile, HarnessSnapshot


class ComponentRegistry:
    def __init__(self, adapters=()):
        self.adapters = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter):
        document = adapter.snapshot()
        if document.component_id in self.adapters:
            raise ValueError('duplicate component owner: ' + document.component_id)
        self.adapters[document.component_id] = adapter

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


class TextComponentAdapter:
    """Reuse existing prompt/guidance/retained/workflow validation and projection."""
    def __init__(self, target, kind):
        self.target, self.kind = target, kind
        self.required_capabilities: frozenset[str] = getattr(target, 'required_capabilities', frozenset())

    def snapshot(self):
        value = self.target.snapshot()
        return ComponentDocument(value.target_id, self.kind, value.role, value.schema,
                                 (ComponentFile('instructions.txt', value.text),))

    def validate(self, document):
        if len(document.files) != 1 or document.files[0].path != 'instructions.txt':
            raise ValueError('this object owns one instruction file')
        if document != self.snapshot():
            self.target.validate(document.files[0].text)

    def prepare_trial(self, config, document):
        self.validate(document)
        if not document.files[0].text and document == self.snapshot():
            return config
        config = self.target.prepare_trial(config, document.files[0].text)
        execution = getattr(self.target, 'prepare_execution', None)
        return execution(config, document.files[0].text) if execution is not None else config

    def to_text(self, document):
        self.validate(document)
        return document.files[0].text


class FileComponentAdapter:
    """An explicitly installed source component with injected object validation.

    Registration alone grants no execution capability. The runner must install
    the declared component. Compile checks do not establish correctness.
    """
    def __init__(self, document, validate):
        self.document, self.validator = document, validate

    def snapshot(self):
        return self.document

    def validate(self, document):
        self.validator(document)


def component_registry(targets):
    adapters = []
    for target in targets:
        snapshot = target.snapshot()
        if snapshot.binding.kind == 'components':
            continue
        kind = getattr(target, 'component_kind', 'retained-document' if snapshot.role == 'S' else 'instructions')
        adapters.append(TextComponentAdapter(target, kind))
    return ComponentRegistry(adapters)


def bundle_target(targets):
    from fruitfly_agent.lab.algorithms.components import ComponentTarget
    return ComponentTarget('component-bundle', 'Component bundle',
        tuple(t for t in targets if t.snapshot().binding.kind != 'components'))


def bundle_text(target, harness):
    from .contracts.pipeline import canonical_json
    return canonical_json({t.snapshot().target_id:
        TextComponentAdapter(t, getattr(t, 'component_kind', 'instructions')).to_text(harness.component(t.snapshot().target_id))
        for t in target.targets})


__all__ = ['ComponentRegistry', 'TextComponentAdapter', 'FileComponentAdapter', 'component_registry', 'bundle_target', 'bundle_text']
