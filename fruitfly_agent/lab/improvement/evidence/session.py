"""Shared bounded model workspace session; no editing or scoring policy."""
from __future__ import annotations
import base64
import hashlib
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AgentToolResult, AssistantMessage, ImageBlock, TextBlock, UserMessage
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.core.tool_runtime import AgentTool
from .projections import builtin_evidence_projections

class WorkspaceSession:
    def __init__(self, config, artifacts, *, max_tool_calls=48, page_characters=12000,
                 projection='granted-full', projections=None):
        self.config, self.artifacts, self.max_tool_calls = config, artifacts, max_tool_calls
        if type(page_characters) is not int or not 1 <= page_characters <= 24000:
            raise ValueError('evidence page_characters must be 1..24000')
        self.page_characters = page_characters
        self.projection = (projections or builtin_evidence_projections()).get(projection)

    async def session(self, mission, workspace, services, *, writable=False, system=""):
        count = 0
        def reserve():
            nonlocal count
            services.check()
            if count >= self.max_tool_calls:
                raise ValueError('editor tool allocation exhausted')
            count += 1
        async def listing(ctx):
            reserve()
            return AgentToolResult(content=[TextBlock(text='\n'.join(workspace.paths()))])
        async def read(ctx):
            reserve()
            path = ctx.args['path']
            data = workspace.read(path)
            if data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff'):
                mime = 'image/png' if data.startswith(b'\x89PNG') else 'image/jpeg'
                services.record('editor-evidence-page', path=path, artifact_id='sha256:' + hashlib.sha256(data).hexdigest(),
                                status='image', bytes=len(data), truncated=False)
                return AgentToolResult(content=[ImageBlock(data=base64.b64encode(data).decode('ascii'), media_type=mime)])
            try:
                text = data.decode('utf-8')
            except UnicodeDecodeError:
                services.record('editor-evidence-page', path=path, artifact_id='sha256:' + hashlib.sha256(data).hexdigest(),
                                status='binary-unavailable', bytes=len(data), truncated=False)
                return AgentToolResult(content=[TextBlock(text=f'Binary original: {path}, {len(data)} bytes. No text renderer is installed.')])
            offset, limit = ctx.args.get('offset', 0), ctx.args.get('limit', self.page_characters)
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 24000:
                raise ValueError('read needs nonnegative character offset and limit 1–24000')
            page = self.projection.render(text, offset, limit)
            if not isinstance(page, str) or len(page) > 24000:
                raise ValueError('evidence projection must return bounded text')
            services.record('editor-evidence-page', path=path, artifact_id='sha256:' + hashlib.sha256(data).hexdigest(),
                            projection=self.projection.projection_id, implementation_id=self.projection.implementation_id,
                            returned_sha256=hashlib.sha256(page.encode('utf-8')).hexdigest(),
                            status='text', offset=offset, limit=limit, start=min(offset, len(text)),
                            end=min(offset + limit, len(text)), characters=len(text),
                            truncated=offset + limit < len(text))
            if offset + limit < len(text):
                page += f'\n[Partial text: {len(text)} characters; continue with offset={offset + limit}]'
            return AgentToolResult(content=[TextBlock(text=page)])
        async def write(ctx):
            reserve()
            workspace.write(ctx.args['path'], ctx.args['content'])
            return AgentToolResult(content=[TextBlock(text='Candidate file saved')])
        async def delete(ctx):
            reserve()
            workspace.delete(ctx.args['path'])
            return AgentToolResult(content=[TextBlock(text='Candidate file removed')])
        path_schema = {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']}
        tools = [AgentTool(name='list_files', label='List evidence files', description='List all granted evidence and candidate paths.',
                          parameters={'type': 'object', 'properties': {}}, execute=listing),
                 AgentTool(name='read_file', label='Read evidence', description='Read a granted file. Text uses character offset/limit pagination; PNG/JPEG images are returned visually.',
                    parameters={'type': 'object', 'properties': {'path': {'type': 'string'}, 'offset': {'type': 'integer'},
                                 'limit': {'type': 'integer'}}, 'required': ['path']}, execute=read)]
        if writable:
            tools.extend((AgentTool(name='write_file', label='Write candidate component',
                description='Create or replace a complete UTF-8 file in an editable harness component.',
                parameters={'type': 'object', 'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}},
                            'required': ['path', 'content']}, execute=write),
                AgentTool(name='delete_file', label='Delete candidate file', description='Remove a file from an editable harness component.',
                          parameters=path_schema, execute=delete)))
        def provider(view, *, signal=None):
            services.reserve('model')
            services.record('editor-request', model=view.model, stage=mission[:80])
            async def events():
                try:
                    message = await self.config.provider(view, signal=services.signal).result()
                    services.record('editor-response', status='completed', text=message.text)
                    yield StreamDone(message)
                except BaseException:
                    services.record('editor-response', status='interrupted')
                    raise
            return AssistantMessageEventStream(events())
        config = AgentLoopConfig(provider=provider, model=self.config.model,
            max_tokens=self.config.max_tokens, context_window=self.config.context_window,
            system_prompt=system + '\n' + mission, tools=tuple(tools), max_turns=12,
            max_tool_calls_per_turn=self.max_tool_calls)
        result = await run_agent_loop(config, [UserMessage(content='Use the supplied workspace to perform this stage.')], signal=services.signal)
        services.check()
        answers = [m for m in result.messages if isinstance(m, AssistantMessage)]
        if result.is_error or not answers or answers[-1].stop_reason != 'stop' or answers[-1].tool_calls:
            raise ValueError('editor did not finish its stage')
        return answers[-1].text

