"""Owner defaults and receipts through the existing Catalog; no second registry."""
from dataclasses import replace
from fruitfly_agent.runtime_spec.components import ComponentConfiguration
from fruitfly_agent.runtime_spec.documents import package_document
from .parameters import decode_parameters


def read_default(catalog, component_id):
    from .configuration import configuration_surfaces
    surfaces = configuration_surfaces(catalog)
    if component_id in surfaces:
        _, surface = surfaces[component_id]
        resource, role = surface.default_resource, surface.role
        fallback = surface.default() if surface.default is not None else None
    else:
        definition = catalog.get(component_id)
        resource, role = definition.default_resource, definition.configuration_role
        from .parameters import encode_parameters
        fallback = encode_parameters(definition, {p.name: p.default for p in definition.descriptor.parameters
            if p.name not in {r.parameter for r in definition.model_role_parameters.values()}})
    receipt = None
    if resource is None:
        if fallback is None:
            raise ValueError('component has no registered defaults: ' + component_id)
        document = ComponentConfiguration(component_id, role, component_id, fallback)
    else:
        value, receipt = package_document(*resource)
        document = ComponentConfiguration.from_dict(value)
        if document.id != component_id or document.implementation != component_id or document.role != role:
            raise ValueError('registered default component ID/role differs from its owner: ' + component_id)
        if document.artifacts or not document.enabled:
            raise ValueError('registered defaults cannot contain adopted artifacts or disable their owner')
    return document, receipt


def resolve_defaults(profile, catalog):
    documents, sources = [], {source.path: source for source in profile.source_files}
    for document in profile.component_documents:
        if document.reference.get('default') is True:
            default, receipt = read_default(catalog, document.id)
            if default.role != document.role:
                raise ValueError('default component ID/role differs from its configuration position: ' + document.id)
            document = replace(default, enabled=document.enabled,
                reference=document.reference, source=receipt.path if receipt else 'registered default: ' + document.id)
            if receipt is not None:
                sources[receipt.path] = receipt
        documents.append(document)
    return replace(profile, component_documents=tuple(documents), source_files=tuple(sources.values()))


def declared_defaults(definition):
    """Bind descriptor defaults to one owner document before target installation."""
    if definition.default_resource is None:
        return definition
    value, _ = package_document(*definition.default_resource)
    document = ComponentConfiguration.from_dict(value)
    if (document.id, document.implementation, document.role) != (definition.descriptor.mechanism_id,
            definition.descriptor.mechanism_id, definition.configuration_role):
        raise ValueError('registered defaults differ from their owner')
    if document.artifacts or not document.enabled:
        raise ValueError('registered defaults cannot contain adopted artifacts or disable their owner')
    values = decode_parameters(definition, dict(document.parameters))
    role_fields = {r.parameter for r in definition.model_role_parameters.values()}
    expected = {p.name for p in definition.descriptor.parameters} - role_fields
    if set(values) != expected:
        raise ValueError('registered defaults must declare every non-model parameter exactly once: ' + document.id)
    descriptors = tuple(replace(p, default=values[p.name]) if p.name in values else p
                        for p in definition.descriptor.parameters)
    return replace(definition, descriptor=replace(definition.descriptor, parameters=descriptors))
