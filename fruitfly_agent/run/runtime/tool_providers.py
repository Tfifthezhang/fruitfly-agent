"""Prepare registered external tool providers through public Catalog contracts."""
from fruitfly_agent.lab.catalog import PreparedToolProvider, ToolProviderContext


async def prepare_tool_providers(profile, catalog, *, workspace, environment, approve_start, resources, artifacts):
    prepared: dict[str, PreparedToolProvider] = {}
    def own(resource):
        if not any(item is resource for item in resources):
            resources.append(resource)
        return resource
    async def deny(plan):
        return False
    context = ToolProviderContext(workspace, environment.get, approve_start or deny, own,
        lambda text: artifacts.put_text(text).artifact_id, artifacts.read_text)
    for item in catalog.resolve(profile.mechanisms):
        prepare = item.definition.tool_provider
        if prepare is None:
            continue
        result = await prepare(item.parameters, context)
        if not isinstance(result, PreparedToolProvider):
            raise TypeError('tool provider preparation must return PreparedToolProvider')
        for resource in result.resources:
            own(resource)
        names = [tool.name for tool in result.tools]
        if len(names) != len(set(names)) or set(result.policies) != set(names):
            raise ValueError('prepared external tools require distinct names and one policy per tool')
        if any(tool.permission is None or tool.permission.operation != 'external_tool' for tool in result.tools):
            raise ValueError('prepared external tools must declare external_tool permissions')
        if any(set(names) & {tool.name for tool in other.tools} for other in prepared.values()):
            raise ValueError('prepared tool providers declared conflicting tool names')
        prepared[item.definition.descriptor.mechanism_id] = result
    return prepared
