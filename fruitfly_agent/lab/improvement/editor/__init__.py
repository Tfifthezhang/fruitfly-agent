"""The default tool-using editor; all algorithms share the generator protocol."""
from __future__ import annotations

import base64
import json

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AgentToolResult, AssistantMessage, ImageBlock, TextBlock, UserMessage, ProviderView
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.core.tool_runtime import AgentTool
from ..contracts.pipeline import (CandidateBundle, EditReason, ExperienceEntry,
    ComponentDocument, ComponentFile, CompositionRequest, HarnessSnapshot, SelectionDecision, canonical_json)
from ..evidence import EvidenceWorkspace
from .instructions import EditorInstructions


def model_completion(config):
    """One tool-free request for non-Agent generators; the caller owns accounting."""
    async def complete(system, prompt, *, signal):
        result = await config.provider(ProviderView(system, [UserMessage(content=prompt)], [],
            config.model, config.max_tokens), signal=signal).result()
        if result.stop_reason != 'stop' or result.tool_calls:
            raise ValueError('generator model completion did not finish')
        return result.text
    return complete



class AgentEditor:
    implementation_id = 'workspace-editor-v1'

    def __init__(self, config, artifacts, components, *, max_tool_calls=48, instructions=None):
        self.config, self.artifacts, self.components = config, artifacts, components
        self.max_tool_calls = max_tool_calls
        self.instructions = instructions or EditorInstructions()

    async def session(self, mission, workspace, services, *, writable=True):
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
                return AgentToolResult(content=[ImageBlock(data=base64.b64encode(data).decode('ascii'), media_type=mime)])
            try:
                text = data.decode('utf-8')
            except UnicodeDecodeError:
                return AgentToolResult(content=[TextBlock(text=f'Binary original: {path}, {len(data)} bytes. No text renderer is installed.')])
            offset, limit = ctx.args.get('offset', 0), ctx.args.get('limit', 12000)
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 24000:
                raise ValueError('read needs nonnegative character offset and limit 1–24000')
            page = text[offset:offset + limit]
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
            system_prompt=self.instructions.system + '\n' + mission, tools=tuple(tools), max_turns=12,
            max_tool_calls_per_turn=self.max_tool_calls)
        result = await run_agent_loop(config, [UserMessage(content='Use the supplied workspace to perform this stage.')], signal=services.signal)
        services.check()
        answers = [m for m in result.messages if isinstance(m, AssistantMessage)]
        if result.is_error or not answers or answers[-1].stop_reason != 'stop' or answers[-1].tool_calls:
            raise ValueError('editor did not finish its stage')
        return answers[-1].text

    async def edit(self, stage, request, services):
        workspace = EvidenceWorkspace.build(request, self.artifacts, record=services.record)
        mission = getattr(self.instructions, request.scope) if stage == 'propose' else self.instructions.compose
        mission += ('\nAfter editing return only JSON {"reasons":[{"component_id":"...",'
            '"explanation":"...","evidence_ids":["run-id"]}]}. Each changed component needs a supplied run ID; no changes is valid.')
        mission += '\nUser guidance: ' + request.plan.direction
        for attempt in range(2):
            response = await self.session(mission, workspace, services)
            try:
                value = json.loads(response)
                if not isinstance(value, dict) or set(value) != {'reasons'}:
                    raise ValueError('editor must return exactly a reasons array')
                reasons = tuple(EditReason(**r) for r in value['reasons'])
                candidate = CandidateBundle(request.plan.parent, request.baseline, workspace.collect(),
                                            request.plan.generator_id, reasons)
                self.components.validate(candidate.harness)
                changed = set(candidate.changed_ids)
                known = {r.run_id for r in request.records}
                if ({r.component_id for r in reasons} != changed
                        or any(set(r.evidence_ids) - known for r in reasons)):
                    raise ValueError('each changed component must cite supplied executions')
                return candidate
            except (ValueError, TypeError, KeyError) as exc:
                services.record('editor-invalid', attempt=attempt + 1, reason=str(exc))
                mission = mission + '\nRepair the candidate and its result: ' + str(exc)
        services.record('editor-fallback', baseline_id=request.baseline.snapshot_id)
        return CandidateBundle(request.plan.parent, request.baseline, request.baseline, request.plan.generator_id)


class AgentSelector:
    def __init__(self, editor, services):
        self.editor, self.services = editor, services

    async def select(self, task, records):
        placeholder = HarnessSnapshot((ComponentDocument('selection', 'selection', 'H', 'selection-v1', ()),))
        files = {'context/task.md': task.instruction.encode('utf-8')}
        mapping = {}
        for index, record in enumerate(records):
            label = str(index + 1)
            mapping[label] = record.run_id
            files[f'context/candidates/{label}/output.txt'] = record.output.encode('utf-8')
            for resource in record.artifacts:
                if resource.kind == 'deliverable':
                    files[f'context/candidates/{label}/' + resource.path] = self.editor.artifacts.read(resource.artifact_id)
        for resource in task.inputs:
            files['context/inputs/' + resource.path] = self.editor.artifacts.read(resource.artifact_id)
        files['INDEX.json'] = canonical_json({'files': sorted(files), 'candidate_ids': list(mapping)}).encode('utf-8')
        workspace = EvidenceWorkspace(baseline=placeholder, files=files, writable_ids=())
        response = await self.editor.session(
            self.editor.instructions.select,
            workspace, self.services, writable=False)
        try:
            if response.strip() == 'NO_CLEAR_CHOICE':
                return SelectionDecision(records[0].run_id, 'Insufficient distinction; baseline retained')
            value = json.loads(response)
            return SelectionDecision(mapping[value['choice']], value['reason'])
        except (ValueError, TypeError, KeyError):
            self.services.record('selection-invalid', reason='Malformed choice; baseline retained')
            return SelectionDecision(records[0].run_id, 'Invalid selection; baseline retained')


class AgentReflector:
    def __init__(self, editor, services):
        self.editor, self.services = editor, services

    async def reflect(self, outcome):
        request = CompositionRequest(outcome.plan, outcome.task,
            outcome.candidates[0].base if outcome.candidates else outcome.harness,
            outcome.candidates, outcome.records, 0)
        workspace = EvidenceWorkspace.build(request, self.editor.artifacts, record=self.services.record)
        response = await self.editor.session(
            self.editor.instructions.reflect,
            workspace, self.services, writable=False)
        if response.strip() == 'NO_ENTRY':
            return ()
        value = json.loads(response)
        cited = [r for r in outcome.records if r.run_id in value['evidence_ids'] and r.status == 'completed']
        if len({r.harness_id for r in cited}) < 2 or len(cited) != len(set(value['evidence_ids'])):
            raise ValueError('a lesson requires observed contrasts from distinct executed harnesses')
        return (ExperienceEntry('experience-' + outcome.plan.job_id, outcome.task.task_id,
            value['cue'], value['lesson'], tuple(value['evidence_ids']), outcome.harness, value.get('limitations', '')),)


__all__ = ['AgentEditor', 'AgentSelector', 'AgentReflector', 'model_completion']
