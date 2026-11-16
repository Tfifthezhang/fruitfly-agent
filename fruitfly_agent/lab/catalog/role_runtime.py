"""Assemble owner-declared context mechanisms for restricted Agent hosts."""
from dataclasses import replace
from .catalog import LabCatalog
from .assembly import assemble_lab


def assemble_role(config, *, catalog, selections, context):
    """Retain effective context policy without importing ambient tools or state.

    Applicability is protected owner metadata. Missing dependencies are errors,
    never a reason to silently disable an explicitly selected context mechanism.
    The host must supply an actual scoped reader before declaring resource-reader.
    """
    selected = tuple(s for s in selections if catalog.get(s.mechanism_id).role_safe)
    role_catalog = LabCatalog(tuple(catalog.get(s.mechanism_id) for s in selected), bootstrap=catalog.bootstrap)
    slots = frozenset(slot for definition in role_catalog.definitions() for slot in definition.artifact_slots)
    context = replace(context, artifact_bindings={key: value for key, value in context.artifact_bindings.items() if key in slots})
    result = assemble_lab(config, catalog=role_catalog, selections=selected, context=context)
    inventory = {'components': [
        {'id': item.definition.descriptor.mechanism_id, 'parameters': dict(item.parameters),
         'implementation_id': item.definition.implementation_id}
        for item in catalog.resolve(selected, capabilities=context.host_capabilities)],
        'excluded': [s.mechanism_id for s in selections if s.enabled and s not in selected],
        'context_pipeline': result.context_pipeline.profile.to_dict() if result.context_pipeline else None}
    return result, inventory
