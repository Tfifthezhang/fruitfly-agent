"""Shared bounded model workspace session; no editing or scoring policy."""
from __future__ import annotations
import base64
import hashlib
import json
from fruitfly_agent.lab.improvement.evidence.query import search_text
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AgentToolResult, AssistantMessage, ImageBlock, TextBlock, UserMessage
from fruitfly_agent.core.data_model.media import image_type, validate_image, decode_text_file
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.core.tool_runtime import AgentTool
from .evidence.projections import builtin_evidence_projections

class WorkspaceSession:
    def __init__(self, config, artifacts, *, max_tool_calls=48, max_turns=12, page_characters=12000,
                 projection='granted-full', projections=None, access_mode='search'):
        self.config, self.artifacts, self.max_tool_calls = config, artifacts, max_tool_calls
        if type(page_characters) is not int or not 1 <= page_characters <= 24000:
            raise ValueError('evidence page_characters must be 1..24000')
        self.page_characters = page_characters
        if type(max_turns) is not int or not 1 <= max_turns <= 256:
            raise ValueError('editor max_turns must be 1..256')
        self.max_turns = max_turns
        if type(max_tool_calls) is not int or not 1 <= max_tool_calls <= 256:
            raise ValueError('editor max_tool_calls must be 1..256')
        if access_mode not in {'paged', 'search'}:
            raise ValueError('evidence access_mode must be paged or search')
        self.access_mode = access_mode
        self.projection = (projections or builtin_evidence_projections()).get(projection)

    async def session(self, mission, workspace, services, *, writable=False, system="", submit=None):
        from .evidence.access import EvidenceAccess
        # Read-only embedding workspaces retain the original minimal protocol.
        access = getattr(workspace, 'access', None)
        if access is None:
            access = EvidenceAccess(record=services.record)
        access.grant(workspace.paths())
        count = 0
        submitted = None
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
            try:
                data = workspace.read(path)
            except (KeyError, ValueError, OSError):
                access.failed(path)
                raise
            access.available(path)
            if image_type(data) is not None:
                mime = validate_image(data)
                services.record('editor-evidence-page', path=path, artifact_id='sha256:' + hashlib.sha256(data).hexdigest(),
                                status='image', bytes=len(data), truncated=False)
                access.provided(path, data)
                return AgentToolResult(content=[ImageBlock(data=base64.b64encode(data).decode('ascii'), media_type=mime)])
            try:
                text = decode_text_file(data)
            except ValueError:
                access.failed(path)
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
            access.provided(path, page, offset=offset)
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
        async def search(ctx):
            reserve()
            try:
                data = workspace.read(ctx.args['path'])
                access.available(ctx.args['path'])
                result = search_text(data.decode('utf-8'), ctx.args['query'],
                    offset=ctx.args.get('offset', 0), limit=ctx.args.get('limit', 20))
            except (KeyError, ValueError, OSError):
                access.failed(ctx.args['path'])
                raise
            for match in result['matches']:
                access.provided(ctx.args['path'], match['text'], offset=match['offset'])
            reference = 'sha256:' + hashlib.sha256(data).hexdigest()
            services.record('editor-evidence-search', path=ctx.args['path'], artifact_id=reference,
                query=ctx.args['query'], offsets=[m['offset'] for m in result['matches']],
                next_offset=result['next_offset'])
            return AgentToolResult(content=[TextBlock(text=json.dumps(result, ensure_ascii=False))])
        async def seal(ctx):
            nonlocal submitted
            if submit is None:
                raise ValueError('this stage has no submission capability')
            submit(ctx.args)
            submitted = json.dumps(ctx.args, ensure_ascii=False)
            return AgentToolResult(content=[TextBlock(text='Candidate validated and submitted')], terminate=True)
        path_schema = {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']}
        tools = [AgentTool(name='list_files', label='List evidence files', description='List all granted evidence and candidate paths.',
                          parameters={'type': 'object', 'properties': {}}, execute=listing),
                 AgentTool(name='read_file', label='Read evidence', description='Read a granted file. Text uses character offset/limit pagination; PNG/JPEG/GIF/WebP images up to 10 MiB are returned visually.',
                    parameters={'type': 'object', 'properties': {'path': {'type': 'string'}, 'offset': {'type': 'integer'},
                                 'limit': {'type': 'integer'}}, 'required': ['path']}, execute=read)]
        if writable:
            tools.extend((AgentTool(name='write_file', label='Write candidate component',
                description='Create or replace a complete UTF-8 file in an editable harness component.',
                parameters={'type': 'object', 'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}},
                            'required': ['path', 'content']}, execute=write),
                AgentTool(name='delete_file', label='Delete candidate file', description='Remove a file from an editable harness component.',
                          parameters=path_schema, execute=delete)))
        if self.access_mode == 'search':
            tools.append(AgentTool(name='search_file', label='Search granted evidence',
                description='Find literal text in one granted file. Returns source character offsets and bounded excerpts; use read_file to inspect context.',
                parameters={'type': 'object', 'properties': {'path': {'type': 'string'},
                    'query': {'type': 'string'}, 'offset': {'type': 'integer'}, 'limit': {'type': 'integer'}},
                    'required': ['path', 'query']}, execute=search))
        if writable and submit is not None:
            tools.append(AgentTool(name='submit_candidate', label='Submit candidate',
                description='Validate and submit the current candidate with one evidence-grounded reason per changed component. Ends this editing stage on success.',
                parameters={'type': 'object', 'properties': {'reasons': {'type': 'array', 'items': {
                    'type': 'object', 'properties': {'component_id': {'type': 'string'},
                        'explanation': {'type': 'string'}, 'evidence_ids': {'type': 'array', 'items': {'type': 'string'}}},
                    'required': ['component_id', 'explanation', 'evidence_ids'], 'additionalProperties': False}}},
                    'required': ['reasons'], 'additionalProperties': False}, execute=seal))
        def provider(view, *, signal=None):
            services.reserve('model')
            services.record('editor-request', model=view.model, stage=mission[:80])
            async def events():
                inner = None
                try:
                    inner = self.config.provider(view, signal=services.signal)
                    async for event in inner:
                        yield event
                    message = await inner.result()
                    services.record('editor-response', status='completed', text=message.text)
                    yield StreamDone(message)
                except BaseException:
                    services.record('editor-response', status='interrupted')
                    raise
                finally:
                    if inner is not None:
                        await inner.aclose()
            return AssistantMessageEventStream(events())
        from fruitfly_agent.core.context.budget import forward_context_capabilities
        forward_context_capabilities(provider, self.config.provider)
        config = AgentLoopConfig(provider=provider, model=self.config.model,
            context_meter=self.config.context_meter,
            max_tokens=self.config.max_tokens, context_window=self.config.context_window,
            system_prompt=system + '\n' + mission, tools=tuple(tools), max_turns=self.max_turns,
            max_tool_calls_per_turn=self.max_tool_calls + (1 if submit is not None else 0))
        result = await run_agent_loop(config, [UserMessage(content='Use the supplied workspace to perform this stage.')], signal=services.signal)
        services.check()
        if submitted is not None:
            return submitted
        answers = [m for m in result.messages if isinstance(m, AssistantMessage)]
        if result.is_error or not answers or answers[-1].stop_reason != 'stop' or answers[-1].tool_calls:
            raise ValueError('editor did not finish its stage')
        return answers[-1].text

