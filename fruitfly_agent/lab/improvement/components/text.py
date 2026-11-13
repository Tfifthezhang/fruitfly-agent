"""Owned component adapters and validation."""
from fruitfly_agent.improvement.contracts.components import ComponentDocument, ComponentFile, HarnessSnapshot
from fruitfly_agent.improvement.components.registry import ComponentRegistry
from fruitfly_agent.improvement.contracts.components import ComponentBinding


from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec, OptimizationField


class TextComponentAdapter:
    """A typed YAML parameter document over the owner's existing execution codec."""
    def __init__(self, target, kind):
        self.target, self.kind = target, kind
        if not isinstance(getattr(target, 'optimization', None), OptimizationSpec):
            raise ValueError('parameter owner must explicitly declare its optimization surface')
        self.required_capabilities = target.optimization.required_capabilities

    @property
    def optimization(self):
        return self.target.optimization

    def _values(self, text):
        encode = getattr(self.target, 'parameter_values', None)
        if encode is not None:
            return encode(text)
        if getattr(self.target, 'structured_parameters', False):
            import json
            return json.loads(text)
        name = getattr(self.target, 'optimization_field',
            'content.body' if self.optimization.representation == 'documents' else 'instructions.usage')
        group, field = name.split('.', 1)
        return {group: {field: text}}

    def _text(self, parameters):
        decode = getattr(self.target, 'parameter_text', None)
        if decode is not None:
            return decode(parameters)
        if getattr(self.target, 'structured_parameters', False):
            from fruitfly_agent.improvement.contracts.versions import canonical_json
            return canonical_json(parameters)
        expected = self._values('')
        if not isinstance(parameters, dict) or set(parameters) != set(expected):
            raise ValueError('candidate must preserve its registered parameter groups')
        group = next(iter(expected))
        field = next(iter(expected[group]))
        if not isinstance(parameters[group], dict) or set(parameters[group]) != {field}:
            raise ValueError('candidate changed protected parameter fields')
        return parameters[group][field]

    def snapshot(self):
        import yaml
        value = self.target.snapshot()
        parameters = {'id': value.target_id, 'role': value.role,
            'implementation': value.target_id, 'parameters': self._values(value.text)}
        return ComponentDocument(value.target_id, self.kind, value.role, value.schema,
            (ComponentFile('parameters.yaml', yaml.safe_dump(parameters, sort_keys=False, allow_unicode=True)),))

    def _read(self, document):
        expected_document = self.snapshot()
        if (document.component_id, document.role, document.kind, document.schema) != (
                expected_document.component_id, expected_document.role,
                expected_document.kind, expected_document.schema):
            raise ValueError('component ownership cannot change')
        import yaml
        from fruitfly_agent.core.configuration_resources import UniqueLoader
        from fruitfly_agent.runtime_spec.components import ComponentConfiguration
        if len(document.files) != 1 or document.files[0].path != 'parameters.yaml':
            raise ValueError('this owner requires one parameters.yaml document')
        value = ComponentConfiguration.from_dict(yaml.load(document.files[0].text, Loader=UniqueLoader))
        expected = self.target.snapshot()
        if ((value.id, value.role, value.implementation) != (expected.target_id, expected.role, expected.target_id)
                or not value.enabled or value.artifacts):
            raise ValueError('candidate changed protected component identity, role or bindings')
        if dict(value.parameters) == self._values(expected.text):
            return expected.text
        return self._text(dict(value.parameters))

    def describe_fields(self, document=None):
        if document is not None:
            self.validate(document)
        describe = getattr(self.target, 'describe_fields', None)
        if describe is not None:
            return describe(self._read(document)) if document is not None else describe()
        if self.optimization.representation not in {'text', 'documents'}:
            raise ValueError('structured component owner must describe its parameters')
        value = self.target.snapshot()
        name = getattr(self.target, 'optimization_field',
            'content.body' if self.optimization.representation == 'documents' else 'instructions.usage')
        description = getattr(self.target, 'description', '') or type(self.target).__doc__
        if not description:
            raise ValueError('parameter owner must describe its content')
        current = self._read(document) if document is not None else value.text
        return (OptimizationField('parameters.' + name, 'string', description.strip(), current, value.text,
            unit='characters', constraints='Owner validation and the experiment grant remain authoritative.'),)

    def validate(self, document):
        text = self._read(document)
        if document != self.snapshot() and text == self.target.snapshot().text:
            raise ValueError('candidate must change effective parameters, not only YAML formatting')
        if text != self.target.snapshot().text:
            self.target.validate(text)

    def validate_options(self, options):
        validate = getattr(self.target, 'validate_options', None)
        if validate is None:
            raise ValueError('component does not declare editable options')
        validate(options)

    def validate_change(self, document, options):
        self.target.validate_change(self._read(document), options)

    def canonicalize(self, document):
        """Normalize a persisted executable document after ordinary config assembly.

        This does not admit formatting-only edits as new research candidates.
        """
        expected = self.snapshot()
        if (document.component_id, document.role, document.kind, document.schema) != (
                expected.component_id, expected.role, expected.kind, expected.schema):
            raise ValueError('component ownership cannot change')
        text = self._read(document)
        if text == self.target.snapshot().text:
            return expected
        self.target.validate(text)
        return document

    def prepare_trial(self, config, document):
        self.validate(document)
        text = self._read(document)
        if not text and document == self.snapshot():
            return config
        return self.target.prepare_trial(config, text)

    def to_text(self, document):
        self.validate(document)
        return self._read(document)

    def export(self, document):
        self.validate(document)
        binding = self.target.snapshot().binding
        text = self._read(document)
        export = getattr(self.target, 'export_text', None)
        return ComponentBinding(document.component_id, binding.kind, binding.key,
            export(text) if export is not None else text)


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

