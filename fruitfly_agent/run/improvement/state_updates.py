"""Apply retained S through the same declared component configuration path."""
from fruitfly_agent.improvement.contracts.components import ComponentBinding
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.lab.catalog import bind_component_changes, configure_profile, configuration_surfaces


def retained_profile(profile, store, *, catalog):
    profile = configure_profile(profile, catalog)
    enabled = {item.definition.descriptor.mechanism_id for item in catalog.resolve(profile.mechanisms)}
    active = {name for name, (owner, surface) in configuration_surfaces(catalog).items()
              if surface.role == 'S' and (owner in enabled or surface.standalone)}
    bindings = tuple(ComponentBinding(key, 'configuration', 'component.' + key,
        canonical_json({'content': {'documents': store.artifacts.read_text(reference)}}))
        for key, reference in sorted(store.read()['libraries'].items()) if key in active)
    return bind_component_changes(profile, bindings, catalog=catalog)
