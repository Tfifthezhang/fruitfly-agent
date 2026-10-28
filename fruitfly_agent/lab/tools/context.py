"""Read only the history/artifact capability supplied by a context owner."""
import json
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.core.tool_runtime.authorization import ToolPermission
from fruitfly_agent.core.context.history import ContextHistory


def context_tools(history: ContextHistory):
    async def read(ctx):
        return AgentToolResult(content=[TextBlock(history.read(ctx.args['reference'],
            offset=ctx.args.get('offset', 0), limit=ctx.args.get('limit', 12000)))])
    async def search(ctx):
        return AgentToolResult(content=[TextBlock(json.dumps(history.search(ctx.args['query'],
            limit=ctx.args.get('limit', 20)), ensure_ascii=False))])
    return (AgentTool(name='context_read', label='Read saved context', permission=ToolPermission('context_read', ()),
        description='Read an immutable context artifact or original message by reference. Use character offset/limit to inspect omitted history; available only in this session.',
        parameters={'type': 'object', 'properties': {'reference': {'type': 'string'}, 'offset': {'type': 'integer'},
            'limit': {'type': 'integer'}}, 'required': ['reference'], 'additionalProperties': False}, execute=read),
        AgentTool(name='context_search', label='Search original context', permission=ToolPermission('context_read', ()),
        description='Search public original message text in this session. Returns source references and offsets, not inferred conclusions. Thinking and opaque protocol state are excluded.',
        parameters={'type': 'object', 'properties': {'query': {'type': 'string'}, 'limit': {'type': 'integer'}},
            'required': ['query'], 'additionalProperties': False}, execute=search))
