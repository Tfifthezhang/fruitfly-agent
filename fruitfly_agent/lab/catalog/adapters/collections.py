"""Validated retained collections that use ordinary configuration materialization."""
import json
from dataclasses import dataclass, field
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, ParameterDescriptor

from fruitfly_agent.lab.catalog.adapters.parameters import ParameterTarget
from fruitfly_agent.improvement.contracts.versions import StateSnapshot, SnapshotFile, canonical_json


def parse_documents(text):
    """Reject duplicate keys and bound allocation before parsing retained content."""
    if not isinstance(text, str) or len(text.encode('utf-8')) > 2_000_000:
        raise ValueError('document collection exceeds its byte budget')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate document field: ' + key)
            result[key] = value
        return result
    value = json.loads(text, object_pairs_hook=unique)
    if not isinstance(value, list) or len(value) > 128:
        raise ValueError('document collection requires at most 128 entries')
    return value


@dataclass(frozen=True)
class CollectionSchema:
    """A retained parameter schema, with no installer or mechanism selection."""
    descriptor: MechanismDescriptor
    configuration_role: str = 'S'
    parameter_paths: dict = field(default_factory=lambda: {'documents': 'content.documents'})
    model_role_parameters: dict = field(default_factory=dict)
    default_resource: object = None
    validate_parameters: object = None


class DocumentsTarget(ParameterTarget):
    """Expose content while retaining the owner's immutable identity and source fields."""
    def __init__(self, surface, parameters, *, label, kind, validate_documents, mutable, freeze_documents=None, visible=None):
        descriptor = MechanismDescriptor(surface.id, label,
            'Retained content validated by its owning module.',
            contributions=(MechanismContribution('capability', 'context'),), parameters=(
                ParameterDescriptor('documents', 'string', 'Documents',
                    'Descriptions, bodies and applicability; identity and sources remain protected.', ''),))
        schema = CollectionSchema(descriptor)
        super().__init__(schema, parameters, {'documents'})
        self.kind = kind
        self.visible = visible or (lambda entry: True)
        self.component_kind = surface.kind
        self.optimization = surface.optimization
        def bounded_documents(entries):
            import yaml
            values = validate_documents(entries)
            # Reserve room for the single component file's owner metadata.
            encoded = yaml.safe_dump({'content': {'documents': canonical_json(values)}}, allow_unicode=True)
            if len(encoded) > 118000:
                raise ValueError('retained collection exceeds the editable component text budget')
            return values
        self.validate_documents = bounded_documents
        self.mutable = frozenset(mutable)
        self.freeze_documents = freeze_documents
        self._prepared_change: str | None = None
        self.entries = self.validate_documents(parse_documents(self.values['documents']))

    @property
    def library_id(self):
        return self.definition.descriptor.mechanism_id

    @property
    def retained_documents(self):
        return self.values['documents']

    def validate_change(self, text, options):
        super().validate_change(text, options)
        entries = self.validate_documents(parse_documents(self.parse(text)['documents']))
        if getattr(self, '_prepared_change', None) == canonical_json(entries):
            return
        before = {e['id']: e for e in self.entries}
        after = {e['id']: e for e in entries}
        if set(before) != set(after):
            raise ValueError('optimization must preserve installed document identities')
        for key, entry in before.items():
            if any(after[key][field] != value for field, value in entry.items() if field not in self.mutable):
                raise ValueError('candidate changed protected document metadata: ' + key)

    def with_state_change(self, entries):
        """Bind an already owner-validated update to an isolated downstream trial."""
        from copy import copy
        result = copy(self)
        result._prepared_change = canonical_json(self.validate_documents(entries))
        return result

    def freeze(self):
        return self.freeze_text(self.snapshot().text)

    def freeze_parameters(self, parameters):
        from fruitfly_agent.lab.catalog.parameters import encode_parameters
        values = dict(parameters)
        if 'content' in values:
            values = dict(values['content'])
        if not values:
            values = dict(self.values)
        if values.get('documents') == '':
            values['documents'] = self.retained_documents
        return self.freeze_text(canonical_json(encode_parameters(self.definition, values)))

    def freeze_text(self, text):
        self.validate(text)
        entries = self.validate_documents(parse_documents(self.parse(text)['documents']))
        key = self.definition.descriptor.mechanism_id
        path = '.fruitfly/retained/' + key + '.json'
        extra = self.freeze_documents(entries) if self.freeze_documents is not None else StateSnapshot()
        return StateSnapshot((SnapshotFile(path, canonical_json(entries)), *extra.files),
            roots=(path, *extra.roots))

    def export_text(self, text):
        return canonical_json(self.parameter_values(text))

    def list_entries(self):
        return self.validate_documents(self.entries)

    def read_entry(self, identity):
        entry = next((entry for entry in self.entries if entry['id'] == identity and self.visible(entry)), None)
        if entry is None:
            raise ValueError('retained document identity is unavailable')
        return canonical_json(entry)

    def view_entries(self):
        return [entry for entry in self.list_entries() if self.visible(entry)]


def collection_surface(identity, *, normalize, default_resource, factory):
    """One declaration generates configuration, grants, inventory and runtime target."""
    from fruitfly_agent.lab.catalog.configuration import ConfigurationSurface
    from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec
    def options(fields, bounds):
        if fields != ['parameters.content.documents'] or bounds:
            raise ValueError('collection grants require content.documents without numeric bounds')
        return {'editable_fields': fields, 'bounds': {}}
    return ConfigurationSurface(identity, 'S', 'settings', identity, normalize,
        edit_options=options, default_resource=default_resource,
        optimization=OptimizationSpec('S', 'parameters', required_capabilities=frozenset({'configuration-materialization'})),
        target_factory=factory, kind='retained-collection', schema='mechanism-parameters-v1')
