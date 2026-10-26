"""Project assembled runtime metadata to Interactive's public descriptions."""
from fruitfly_agent.interactive import InteractiveMechanism
from fruitfly_agent.interactive.contracts.models import InteractiveExecutionEnvironment, ToolServiceStatus
from fruitfly_agent.run.configuration.views import display_group, display_section
from fruitfly_agent.lab.catalog import LabCatalog, EXECUTION_ENVIRONMENT_COMPONENT, ExecutionEnvironmentDescription
from fruitfly_agent.run.runtime.assembly import RuntimeAssembly


def describe_tool_services(runtime: RuntimeAssembly) -> tuple[ToolServiceStatus, ...]:
    return tuple(ToolServiceStatus(info.name, info.transport, info.working_directory, info.state,
        info.tools, info.location) for provider in runtime.tool_providers.values() for info in provider.status())


def describe_execution_environment(runtime: RuntimeAssembly) -> InteractiveExecutionEnvironment | None:
    description = runtime.components.get(EXECUTION_ENVIRONMENT_COMPONENT)
    if description is None:
        return None
    if not isinstance(description, ExecutionEnvironmentDescription):
        raise TypeError("execution environment description must implement the public Lab view")
    return InteractiveExecutionEnvironment(description.label, description.working_directory, description.server)


def describe_runtime(
    runtime: RuntimeAssembly, catalog: LabCatalog,
) -> tuple[tuple[str, ...], tuple[InteractiveMechanism, ...], dict[str, str]]:
    visible_mechanism_ids = tuple(
        mechanism_id
        for mechanism_id in runtime.mechanism_ids
        if catalog.get(mechanism_id).visible
    )
    details = tuple(
        InteractiveMechanism(
            mechanism_id,
            catalog.get(mechanism_id).configuration_category or display_group(catalog.get(mechanism_id).descriptor),
            catalog.get(mechanism_id).descriptor.label,
            catalog.get(mechanism_id).descriptor.primary.layer,
            catalog.get(mechanism_id).descriptor.primary.family,
            catalog.get(mechanism_id).descriptor.primary.context_phase,
            display_section(catalog.get(mechanism_id).descriptor),
            (*catalog.get(mechanism_id).descriptor.effects.tools,
             *(tool.name for tool in runtime.tool_providers[mechanism_id].tools))
                if mechanism_id in runtime.tool_providers else tuple(catalog.get(mechanism_id).descriptor.effects.tools),
        )
        for mechanism_id in runtime.component_ids
        if catalog.get(mechanism_id).visible
    )
    tool_categories: dict[str, str] = {}
    for mechanism_id in runtime.component_ids:
        descriptor = catalog.get(mechanism_id).descriptor
        tool_categories.update({name: "tools" for name in descriptor.effects.tools})
    return visible_mechanism_ids, details, tool_categories
