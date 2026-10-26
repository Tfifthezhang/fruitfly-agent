"""The default tool-using editor; all algorithms share the generator protocol."""
from __future__ import annotations

import json

from fruitfly_agent.core.data_model import UserMessage, ProviderView
from ..contracts.pipeline import CandidateBundle, EditReason
from ..evidence import EvidenceWorkspace
from .instructions import EditorInstructions
from ..evidence.session import WorkspaceSession


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

    def __init__(self, config, artifacts, components, *, max_tool_calls=48, instructions=None, page_characters=12000):
        self.config, self.artifacts, self.components = config, artifacts, components
        self.max_tool_calls = max_tool_calls
        self.instructions = instructions or EditorInstructions()
        self.workspace_session = WorkspaceSession(config, artifacts, max_tool_calls=max_tool_calls,
                                                  page_characters=page_characters)

    async def session(self, mission, workspace, services, *, writable=True):
        return await self.workspace_session.session(mission, workspace, services,
            writable=writable, system=self.instructions.system)

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

