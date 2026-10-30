"""Catalog declaration and asynchronous preparation of optional MCP services."""
from dataclasses import replace
from pathlib import Path
import hashlib
import json

from fruitfly_agent.core.mechanisms import MechanismContribution, MechanismDescriptor, MechanismEffects, ParameterDescriptor
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from fruitfly_agent.lab.catalog.tool_providers import PreparedToolProvider, ToolServiceStart
from fruitfly_agent.improvement.contracts.versions import EXPERIMENT_BLOCKERS_COMPONENT
from .config import load_config


def definition():
    return MechanismDefinition(MechanismDescriptor('mcp-tools', 'MCP services',
        'Use explicitly selected tools from local stdio MCP services.',
        contributions=(MechanismContribution('capability', 'tools'),), install_order=25,
        parameters=(ParameterDescriptor('config', 'path', 'Service configuration',
            'Workspace-local YAML file declaring stdio servers and selected tools.', '.fruitfly/mcp.yaml'),),
        effects=MechanismEffects(uses_network=True, writes_files=True, cost_notice='Starts configured local processes; external tools may have independent effects and costs.')),
        install, implementation_id='mcp-stdio-v1', optimization_exemption='External tool transport and schemas are protected service bindings.', tool_provider=prepare,
        implementation_path='fruitfly_agent/lab/mcp/client.py', documentation_path='fruitfly_agent/lab/mcp/README.md',
        input_parameters=('config',))


async def prepare(parameters, context):
    # Optional libraries and the SDK are not imported by Catalog discovery.
    from .client import McpClient
    from .tools import make_tools
    from .results import ResultStore
    from .authorization import ExternalToolPolicy
    path = Path(parameters['config'])
    path = (context.workspace / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(context.workspace.resolve()):
        raise ValueError('MCP configuration must stay inside the local workspace')
    configs = load_config(path, context.workspace)
    if configs:
        from importlib.util import find_spec
        if find_spec('mcp') is None or find_spec('jsonschema') is None:
            raise RuntimeError("MCP support requires: pip install 'fruitfly-agent[mcp]'")
    tools, resources, identities, policies = [], [], [], {}
    for config in configs:
        if not Path(config.cwd).is_dir():
            raise ValueError('MCP working directory does not exist: ' + config.name)
        environment = dict(config.env)
        for destination, variable in config.secret_env.items():
            value = context.secret_resolver(variable)
            if not value:
                raise ValueError('missing MCP secret variable: ' + variable)
            environment[destination] = value
        plan = ToolServiceStart(config.name, config.command, config.args, config.cwd,
            tuple(sorted(environment)))
        if not await context.approve_start(plan):
            raise PermissionError('MCP service startup was not authorized: ' + config.name)
        client = context.own(McpClient(config, environment))
        resources.append(client)
        await client.start()
        store = ResultStore(config, context.write_artifact, context.read_artifact)
        declared, selected = make_tools(client, store)
        identity = {'name': config.name, 'transport': 'stdio', 'location': 'Local host',
            'command': config.command, 'args': list(config.args), 'cwd': config.cwd,
            'env': dict(config.env), 'secret_env': dict(config.secret_env),
            'server': client.server_info, 'protocol': client.protocol,
            'tools': list(selected), 'result_reader': declared[-1].name,
            'limits': {key: getattr(config, key) for key in ('startup_timeout', 'call_timeout', 'close_timeout',
                       'max_result_bytes', 'inline_result_chars', 'max_parallel')}}
        # Store complete declarations as a verified artifact rather than expanding every manifest.
        snapshot = json.dumps(identity, sort_keys=True, ensure_ascii=False)
        reference = context.write_artifact(snapshot)
        identities.append({'name': config.name, 'transport': 'stdio', 'cwd': config.cwd,
            'artifact': reference, 'digest': 'sha256:' + hashlib.sha256(snapshot.encode()).hexdigest(),
            'tools': [tool.name for tool in declared]})
        for tool in declared:
            policies[tool.name] = ExternalToolPolicy(config.name, tool.label, identities[-1])
        tools.extend(declared)
    return PreparedToolProvider(tuple(tools), tuple(resources), tuple(identities), policies,
        lambda: tuple(client.status() for client in resources))


def install(state, context, parameters):
    prepared = context.tool_providers['mcp-tools']
    state = replace(state, config=replace(state.config, tools=(*state.config.tools, *prepared.tools)))
    for index, resource in enumerate(prepared.resources):
        state = state.with_component(f'external-service:{index}', resource)
    if prepared.tools:
        state = state.with_component(EXPERIMENT_BLOCKERS_COMPONENT,
            (*state.components.get(EXPERIMENT_BLOCKERS_COMPONENT, ()),
             'External tool services have no isolated frozen execution backend'))
    return state
