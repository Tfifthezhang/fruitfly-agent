"""Explicitly authorized local MCP protocol check; never calls a model."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import time

from fruitfly_agent.lab.mcp.client import McpClient
from fruitfly_agent.lab.mcp.config import load_config
from fruitfly_agent.lab.mcp.results import ResultStore
from fruitfly_agent.lab.mcp.tools import make_tools
from fruitfly_agent.run import DataArtifactStore


async def run(args):
    workspace = Path(args.workspace).resolve()
    path = (workspace / args.config).resolve()
    if not path.is_relative_to(workspace):
        raise ValueError('configuration must stay inside the workspace')
    configs = load_config(path, workspace)
    if args.service:
        configs = tuple(item for item in configs if item.name == args.service)
    if not configs or args.call and len(configs) != 1:
        raise ValueError('select exactly one enabled service for a call')
    arguments = json.loads(args.arguments)
    if not isinstance(arguments, dict):
        raise ValueError('arguments must be a JSON object')
    artifacts = DataArtifactStore(workspace / '.fruitfly/artifacts')
    for config in configs:
        environment = dict(config.env)
        for destination, name in config.secret_env.items():
            value = os.environ.get(name)
            if not value:
                raise ValueError('missing secret variable: ' + name)
            environment[destination] = value
        client = McpClient(config, environment)
        try:
            started = time.monotonic()
            await client.start()
            tools, _ = make_tools(client, ResultStore(config,
                lambda text: artifacts.put_text(text).artifact_id, artifacts.read_text))
            report = {'service': config.name, 'startup_seconds': round(time.monotonic() - started, 3),
                      'discovered': [item['name'] for item in client.descriptors],
                      'selected': [tool.name for tool in tools]}
            if args.call:
                if args.call not in config.tools:
                    raise ValueError('the requested tool must be explicitly selected in configuration')
                tool = tools[config.tools.index(args.call)]
                validated = tool.validate_arguments(arguments).unwrap()
                reply = await client.call(args.call, validated)
                text = json.dumps(reply, ensure_ascii=False, sort_keys=True)
                if len(text.encode()) > config.max_result_bytes:
                    raise ValueError('reply exceeds the configured byte budget')
                report['reply_artifact'] = artifacts.put_text(text).artifact_id
                report['is_error'] = bool(reply.get('isError', False))
            print(json.dumps(report, ensure_ascii=True))
        finally:
            await client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', default='.')
    parser.add_argument('--config', default='.fruitfly/mcp.yaml')
    parser.add_argument('--allow-start', action='store_true')
    parser.add_argument('--service')
    parser.add_argument('--call')
    parser.add_argument('--arguments', default='{}')
    args = parser.parse_args()
    if not args.allow_start:
        parser.error('--allow-start is required to authorize configured local processes')
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
