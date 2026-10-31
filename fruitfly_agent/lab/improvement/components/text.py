"""Owned component adapters and validation."""
from fruitfly_agent.improvement.contracts.components import ComponentDocument, ComponentFile, HarnessSnapshot
from fruitfly_agent.improvement.components.registry import ComponentRegistry
from fruitfly_agent.improvement.contracts.components import ComponentBinding


from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec, OptimizationField


class TextComponentAdapter:
    """Reuse existing prompt/guidance/retained validation and projection."""
    def __init__(self, target, kind):
        self.target, self.kind = target, kind
        if not isinstance(getattr(target, 'optimization', None), OptimizationSpec):
            raise ValueError('text owner must explicitly declare its optimization surface')
        self.required_capabilities = target.optimization.required_capabilities

    @property
    def optimization(self):
        return self.target.optimization

    def snapshot(self):
        value = self.target.snapshot()
        return ComponentDocument(value.target_id, self.kind, value.role, value.schema,
                                 (ComponentFile('instructions.txt', value.text),))

    def describe_fields(self, document=None):
        if document is not None:
            self.validate(document)
        describe = getattr(self.target, 'describe_fields', None)
        if describe is not None:
            return describe(document.files[0].text) if document is not None else describe()
        if self.optimization.representation not in {'text', 'documents'}:
            raise ValueError('structured component owner must describe its parameters')
        value = self.target.snapshot()
        name = getattr(self.target,'optimization_field', 'content.body' if self.optimization.representation == 'documents' else 'instructions.usage')
        description = getattr(self.target, 'description', '') or type(self.target).__doc__
        if not description:
            raise ValueError('text component owner must describe its content')
        current = document.files[0].text if document is not None else value.text
        return (OptimizationField('parameters.' + name, 'string', description.strip(), current, value.text,
            unit='characters', constraints='Owner validation and the experiment grant remain authoritative.'),)

    def validate(self, document):
        if len(document.files) != 1 or document.files[0].path != 'instructions.txt':
            raise ValueError('this object owns one instruction file')
        if document != self.snapshot():
            self.target.validate(document.files[0].text)

    def validate_options(self, options):
        validate = getattr(self.target, 'validate_options', None)
        if validate is None:
            raise ValueError('component does not declare editable options')
        validate(options)

    def validate_change(self, document, options):
        self.target.validate_change(document.files[0].text, options)

    def prepare_trial(self, config, document):
        self.validate(document)
        if not document.files[0].text and document == self.snapshot():
            return config
        return self.target.prepare_trial(config, document.files[0].text)

    def to_text(self, document):
        self.validate(document)
        return document.files[0].text

    def export(self, document):
        self.validate(document)
        binding = self.target.snapshot().binding
        text=document.files[0].text
        export=getattr(self.target,'export_text',None)
        return ComponentBinding(document.component_id,binding.kind,binding.key,export(text) if export is not None else text)


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
    from fruitfly_agent.lab.improvement.targets.bundle import ComponentTarget
    return ComponentTarget('component-bundle', 'Component bundle',
        tuple(t for t in targets if t.snapshot().binding.kind != 'components'))


def bundle_text(target, harness):
    from fruitfly_agent.improvement.contracts.versions import canonical_json
    return canonical_json({t.snapshot().target_id:
        TextComponentAdapter(t, getattr(t, 'component_kind', 'instructions')).to_text(harness.component(t.snapshot().target_id))
        for t in target.targets})

