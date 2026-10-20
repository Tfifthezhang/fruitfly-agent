"""A detached file-task executor; other environments implement the TaskRunner port."""
from __future__ import annotations

from dataclasses import replace
import base64
from uuid import uuid4

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AgentToolResult, AssistantMessage, ImageBlock, TextBlock, UserMessage
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from ..contracts.pipeline import ExecutionRecord, Resource, relative_path, canonical_json


class FileTaskRunner:
    """Fresh in-memory input/output files per execution, with no shell or ambient I/O.

    This declared environment measures bounded file tasks. Container, SSH and
    project-command execution require their own injected TaskRunner. It does not
    borrow the live Session, tools, callbacks or environment.
    """
    capabilities = frozenset({'file-workspace', 'tool:read', 'tool:write', 'tool:edit'})

    def __init__(self, config, components, artifacts, services):
        self.config, self.components, self.artifacts, self.services = config, components, artifacts, services

    async def execute(self, plan, task, harness):
        files = {r.path: self.artifacts.read(r.artifact_id) for r in task.inputs}
        originals = dict(files)
        calls = 0
        def read_path(path):
            relative_path(path)
            if path not in files:
                raise ValueError('file is not in the isolated task workspace')
            return files[path].decode('utf-8')
        async def read(ctx):
            path = ctx.args['path']
            relative_path(path)
            data = files.get(path, b'')
            if data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff'):
                return AgentToolResult(content=[ImageBlock(data=base64.b64encode(data).decode('ascii'),
                    media_type='image/png' if data.startswith(b'\x89PNG') else 'image/jpeg')])
            text = read_path(ctx.args['path'])
            offset, limit = ctx.args.get('offset', 1), ctx.args.get('limit', 200)
            if type(offset) is not int or offset < 1 or type(limit) is not int or not 1 <= limit <= 500:
                raise ValueError('line offset and limit must be bounded positive integers')
            lines = text.splitlines()
            shown = '\n'.join(lines[offset - 1:offset - 1 + limit])
            if len(shown) > 24000:
                raise ValueError('selected lines exceed the text page allocation')
            if offset - 1 + limit < len(lines):
                shown += f'\n[Continue with offset={offset + limit}]'
            return AgentToolResult(content=[TextBlock(text=shown)])
        def save(path, content):
            relative_path(path)
            if not isinstance(content, str) or len(content.encode('utf-8')) > 120000:
                raise ValueError('task output exceeds its file allocation')
            if sum(len(v) for k, v in files.items() if k != path) + len(content.encode('utf-8')) > 2_000_000:
                raise ValueError('task workspace allocation exhausted')
            files[path] = content.encode('utf-8')
        async def write(ctx):
            save(ctx.args['path'], ctx.args['content'])
            return AgentToolResult(content=[TextBlock(text='Saved task output')])
        async def edit(ctx):
            text = read_path(ctx.args['path'])
            # Reuse the same exact-original replacement semantics as the file tool.
            from fruitfly_agent.lab.tools.edit import apply_text_edits
            _, value = apply_text_edits(text, ctx.args['edits'], ctx.args['path'])
            save(ctx.args['path'], value)
            return AgentToolResult(content=[TextBlock(text='Edited task output')])
        from fruitfly_agent.lab.tools.read import create_read_tool
        from fruitfly_agent.lab.tools.write import create_write_tool
        from fruitfly_agent.lab.tools.edit import create_edit_tool
        tools = tuple(replace(factory(), execute=execute) for factory, execute in (
            (create_read_tool, read), (create_write_tool, write), (create_edit_tool, edit)))
        def provider(view, *, signal=None):
            nonlocal calls
            self.services.reserve('model')
            calls += 1
            self.services.record('task-model-request', task_id=task.task_id, harness_id=harness.snapshot_id)
            async def events():
                message = await self.config.provider(view, signal=self.services.signal).result()
                yield StreamDone(message)
            return AssistantMessageEventStream(events())
        config = AgentLoopConfig(provider=provider, model=self.config.model,
            max_tokens=self.config.max_tokens, context_window=self.config.context_window,
            system_prompt=self.config.system_prompt, tools=tools, max_turns=min(self.config.max_turns, 32))
        for document in harness.components:
            adapter = self.components.adapters[document.component_id]
            required: frozenset[str] = getattr(adapter, 'required_capabilities', frozenset())
            if required - self.capabilities or document.role == 'I':
                if document == adapter.snapshot():
                    continue
                raise ValueError('the file-task runner lacks this component execution capability')
            if callable(getattr(adapter, 'prepare_trial', None)):
                config = adapter.prepare_trial(config, document)
            elif document != adapter.snapshot():
                raise ValueError('the file-task runner cannot install this component')
        result = await run_agent_loop(config, [UserMessage(content=task.instruction)], signal=self.services.signal)
        self.services.check()
        answers = [m for m in result.messages if isinstance(m, AssistantMessage)]
        output = answers[-1].text if answers else ''
        trajectory = canonical_json([m.to_dict() for m in result.messages]).encode('utf-8')
        artifacts = [Resource('trajectory.json', self.artifacts.put(trajectory), 'application/json', 'trajectory')]
        for path, content in files.items():
            if content != originals.get(path):
                artifacts.append(Resource('deliverables/' + path, self.artifacts.put(content),
                                          'application/octet-stream', 'deliverable'))
        status = 'completed' if not result.is_error and result.stop_reason == 'stop' else 'error'
        return ExecutionRecord('run-' + uuid4().hex, task.task_id, task.material_id, harness.snapshot_id,
            plan.parent.state, plan.conditions_id, 'completed' if status == 'completed' else 'error', output, tuple(artifacts), calls)


__all__ = ['FileTaskRunner']
