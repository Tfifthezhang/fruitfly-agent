"""Install one managed delegation service with five model operations."""
from dataclasses import replace
from fruitfly_agent.lab.agents.subagent.service import SubagentService
from fruitfly_agent.lab.agents.subagent.storage import SubagentStore
from fruitfly_agent.lab.agents.subagent.tools import create_tools


def install(state, context, parameters):
    if context.child_runtime_factory is None or context.artifact_store is None or context.session_path is None:
        raise ValueError('subagent requires a host child-runtime factory, artifacts and Session path')
    binding = context.provider_for_role('subagent')
    store = context.own(SubagentStore(context.session_path.parent / (context.session_path.name + '.subagents'), context.artifact_store, index=context.session))
    async def prepare(request):
        return await context.child_runtime_factory(request.identity, binding.profile, (context.component_id,))
    service = context.own(SubagentService(prepare, store,
        **{key: parameters[key] for key in ('max_concurrent', 'max_agents', 'run_timeout_seconds', 'max_model_requests')},
        instructions=parameters['child_instructions']))
    prefix = context.resources.mount('subagent', lambda path: _read(service, path))
    service.result_prefix = prefix
    return replace(state, config=replace(state.config, tools=(*state.config.tools, *create_tools(service, parameters)))).with_component(
        'agent-execution-scope', service).with_component('subagent-monitor', service)


def _read(service, path):
    import json
    parts = path.split('/')
    if len(parts) != 2:
        raise ValueError('subagent resource requires agent and execution IDs')
    row = service.detail(parts[0], parts[1])
    return json.dumps(service.store.read_result(row)).encode()
