"""Install one managed delegation service with five model operations."""
from dataclasses import replace
from fruitfly_agent.lab.agents.subagent.service import SubagentService
from fruitfly_agent.lab.agents.subagent.storage import SubagentStore
from fruitfly_agent.lab.agents.subagent.tools import create_tools
from fruitfly_agent.lab.agents.subagent.configuration import ProtocolSettings, ResultSettings, InheritanceSettings


def install(state, context, parameters):
    if context.child_runtime_factory is None or context.artifact_store is None or context.session_path is None:
        raise ValueError('subagent requires a host child-runtime factory, artifacts and Session path')
    inheritance = InheritanceSettings.from_parameters(parameters)
    child_factory = context.child_runtime_factory
    if inheritance.mode == 'explicit':
        restrict = getattr(child_factory, 'restrict_components', None)
        if restrict is None:
            raise ValueError('child runtime host does not support explicit component grants')
        child_factory = restrict(inheritance.components)
    binding = context.provider_for_role('subagent')
    store = context.own(SubagentStore(context.session_path.parent / (context.session_path.name + '.subagents'), context.artifact_store, index=context.session))
    async def prepare(request):
        return await child_factory(request.identity, binding.profile, (context.component_id,))
    service = context.own(SubagentService(prepare, store,
        **{key: parameters[key] for key in ('max_concurrent', 'max_agents', 'run_timeout_seconds', 'max_model_requests', 'retirement_timeout')},
        instructions=parameters['child_instructions'],
        protocol=ProtocolSettings.from_parameters(parameters), results=ResultSettings.from_parameters(parameters)))
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
