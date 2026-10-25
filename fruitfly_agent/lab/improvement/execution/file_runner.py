"""A detached file-task executor; other environments implement the TaskRunner port."""
from __future__ import annotations

from dataclasses import replace
import base64
import time
from uuid import uuid4

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AgentToolResult, AssistantMessage, ImageBlock, TextBlock, UserMessage
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from ..contracts.pipeline import ExecutionRecord, Resource, relative_path, canonical_json
from .handles import ManagedExecution
from .facts import attach_facts, loop_fact_values, receipt_facts
from ..contracts.facts import BudgetFact


class FileTaskRunner:
    """Fresh in-memory input/output files per execution, with no shell or ambient I/O.

    This declared environment measures bounded file tasks. Container, SSH and
    project-command execution require their own injected TaskRunner. It does not
    borrow the live Session, tools, callbacks or environment.
    """
    capabilities = frozenset({'file-workspace', 'tool:read', 'tool:write', 'tool:edit', 'events', 'stop', 'execution-config'})

    def __init__(self, config, components, artifacts, services, *, tool_names=None):
        self.config, self.components, self.artifacts, self.services = config, components, artifacts, services
        self.tool_names = frozenset({"read", "write", "edit"} if tool_names is None else tool_names)
        self.capabilities = frozenset(c for c in type(self).capabilities if not c.startswith("tool:") or c[5:] in self.tool_names)

    async def start(self, plan, task, harness):
        run_id = 'run-' + uuid4().hex
        async def execute(journal):
            return await self.execute_files(plan, task, harness, run_id=run_id, journal=journal)
        return ManagedExecution(execute, execution_id=run_id, version_id=harness.snapshot_id,
            artifacts=self.artifacts, record=self.services.record, process_events=True)

    async def execute(self, plan, task, harness):
        handle = await self.start(plan, task, harness)
        try:
            return await handle.result()
        finally:
            await handle.aclose()

    async def execute_files(self, plan, task, harness, *, run_id, journal):
        started = time.monotonic()
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
            journal.publish('artifact-written', path=path, artifact_id=self.artifacts.put(files[path]),
                media_type='text/plain; charset=utf-8')
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
        tools = tuple(tool for tool in (replace(factory(), execute=execute) for factory, execute in (
            (create_read_tool, read), (create_write_tool, write), (create_edit_tool, edit))) if tool.name in self.tool_names)
        def provider(view, *, signal=None):
            nonlocal calls
            self.services.reserve('model')
            calls += 1
            journal.publish('model-request', model=view.model, call=calls)
            self.services.record('task-model-request', task_id=task.task_id, harness_id=harness.snapshot_id)
            async def events():
                message = await self.config.provider(view, signal=self.services.signal).result()
                if message.text:
                    journal.publish('assistant-output', artifact_id=self.artifacts.put(message.text.encode('utf-8')),
                        media_type='text/plain; charset=utf-8')
                journal.publish('model-response', stop_reason=message.stop_reason,
                    input_tokens=message.usage.input_tokens if message.usage is not None else None,
                    output_tokens=message.usage.output_tokens if message.usage is not None else None,
                    usage_reported=message.usage is not None and message.usage.total_tokens > 0)
                yield StreamDone(message)
            return AssistantMessageEventStream(events())
        async def observed(name, message, cancelled):
            journal.publish('tool-finished', tool_call_id=message.tool_call_id,
                tool_name=name, is_error=message.is_error, cancelled=cancelled)
        config = AgentLoopConfig(provider=provider, model=self.config.model,
            max_tokens=self.config.max_tokens, context_window=self.config.context_window,
            system_prompt=self.config.system_prompt, tools=tools, max_turns=self.config.max_turns,
            max_tool_calls_per_turn=self.config.max_tool_calls_per_turn,
            max_context_recovery_attempts=self.config.max_context_recovery_attempts,
            tool_execution=self.config.tool_execution,
            on_tool_result=observed)
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
        from fruitfly_agent.runtime_spec import effective_execution
        execution_reference = self.artifacts.put(canonical_json(effective_execution(config)).encode('utf-8'))
        artifacts = [Resource('runtime-execution.json', execution_reference, 'application/json', 'diagnostic'),
                     Resource('trajectory.json', self.artifacts.put(trajectory), 'application/json', 'trajectory')]
        for path, content in files.items():
            if content != originals.get(path):
                artifacts.append(Resource('deliverables/' + path, self.artifacts.put(content),
                                          'application/octet-stream', 'deliverable'))
        status = 'completed' if not result.is_error and result.stop_reason == 'stop' else 'error'
        record = ExecutionRecord(run_id, task.task_id, task.material_id, harness.snapshot_id,
            plan.parent.state, plan.conditions_id, 'completed' if status == 'completed' else 'error', output, tuple(artifacts), calls)
        values = loop_fact_values(result.diagnostics)
        values['budgets'] = (*values.get('budgets', ()), BudgetFact('model_calls', 'execution', calls,
            source='budgeted file-task Provider'))
        facts = receipt_facts(record, self.artifacts, elapsed_seconds=time.monotonic() - started, **values)
        return attach_facts(record, facts, self.artifacts)


__all__ = ['FileTaskRunner']
