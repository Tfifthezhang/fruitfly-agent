"""Resource-based media file saving.

Resources are supplied by the host; tools never resolve host artifact paths.
"""
from __future__ import annotations

from typing import Callable

from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.data_model.media import MAX_IMAGE_BYTES
from fruitfly_agent.core.tool_runtime import AgentTool, ToolCallContext
from fruitfly_agent.core.tool_runtime.authorization import ToolPermission
from .file_queue import with_file_mutation_queue
from .path_utils import normalize_tool_path


def create_save_media_tool(read_resource: Callable[[str], bytes] | None = None) -> AgentTool:
    async def execute(ctx: ToolCallContext) -> AgentToolResult:
        if ctx.env is None or read_resource is None:
            raise RuntimeError('save_media requires an execution environment and a host media resource reader')
        data = read_resource(ctx.args['resource_id'])
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError('media resource exceeds the 10 MiB save limit')
        resolved = ctx.env.absolute_path(normalize_tool_path(ctx.args['path']))
        if not resolved.is_ok:
            raise RuntimeError('could not resolve media destination: ' + str(resolved.error))
        path = resolved.unwrap()

        async def write() -> AgentToolResult:
            result = ctx.env.write_file(path, data)
            if not result.is_ok:
                raise RuntimeError('could not save media: ' + str(result.error))
            return AgentToolResult([TextBlock(f'Saved {len(data)} bytes to {ctx.args["path"]}')])

        return await with_file_mutation_queue(ctx.env, path, write)

    return AgentTool(name='save_media', label='Save media',
        description='Save an existing media resource by its resource_id to a file in the selected local or SSH environment. '
                    'Use resource IDs supplied by attachments or tool results. Writes original bytes, up to 10 MiB; '
                    'overwrites the destination and creates parent directories. Does not generate or convert media.',
        parameters={'type': 'object', 'properties': {
            'path': {'type': 'string', 'description': 'Destination path in the execution environment'},
            'resource_id': {'type': 'string', 'description': 'Content-addressed media ID supplied in this session'}},
            'required': ['path', 'resource_id'], 'additionalProperties': False},
        permission=ToolPermission('write', ('path',)), execute=execute)
