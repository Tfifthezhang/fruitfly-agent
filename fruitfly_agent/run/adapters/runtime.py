"""Project assembled runtime metadata to Interactive's public descriptions."""
from fruitfly_agent.interactive import InteractiveMechanism
from fruitfly_agent.run.configuration.views import display_group, display_section


def describe_runtime(runtime, catalog):
    visible_mechanism_ids = tuple(
        mechanism_id
        for mechanism_id in runtime.mechanism_ids
        if catalog.get(mechanism_id).visible
    )
    details = tuple(
        InteractiveMechanism(
            mechanism_id,
            display_group(catalog.get(mechanism_id).descriptor),
            catalog.get(mechanism_id).descriptor.label,
            catalog.get(mechanism_id).descriptor.primary.layer,
            catalog.get(mechanism_id).descriptor.primary.family,
            catalog.get(mechanism_id).descriptor.primary.context_phase,
            display_section(catalog.get(mechanism_id).descriptor),
        )
        for mechanism_id in visible_mechanism_ids
    )
    tool_categories: dict[str, str] = {}
    for mechanism_id in runtime.component_ids:
        descriptor = catalog.get(mechanism_id).descriptor
        tool_categories.update({name: "tools" for name in descriptor.effects.tools})
    return visible_mechanism_ids, details, tool_categories
