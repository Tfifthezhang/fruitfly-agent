"""Apply retained S through the same declared component configuration path."""
from fruitfly_agent.improvement.contracts.components import ComponentBinding
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.lab.catalog import bind_component_changes


def retained_profile(profile, store):
    active = {s.mechanism_id for s in profile.mechanisms if s.enabled}
    bindings = tuple(ComponentBinding(key, 'configuration', 'component.' + key,
        canonical_json({'documents': store.artifacts.read_text(reference)}))
        for key, reference in sorted(store.read()['libraries'].items()) if key in active)
    return bind_component_changes(profile, bindings)
