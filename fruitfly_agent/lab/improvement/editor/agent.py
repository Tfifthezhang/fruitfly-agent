"""The default tool-using editor; all algorithms share the generator protocol."""
from __future__ import annotations

import json

from fruitfly_agent.core.data_model import UserMessage, ProviderView
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from ..evidence import EvidenceWorkspace
from ..evidence.access import EvidenceUnavailable
from .instructions import EditorInstructions
from ..workspaces import WorkspaceSession
from .submission import submission
from fruitfly_agent.improvement.workflow.budget import AllocationExhausted


def model_completion(config):
    """One tool-free request for non-Agent generators; the caller owns accounting."""
    async def complete(system, prompt, *, signal):
        stream = config.provider(ProviderView(system, [UserMessage(content=prompt)], [],
            config.model, config.max_tokens), signal=signal)
        try:
            result = await stream.result()
        finally:
            await stream.aclose()
        if result.stop_reason != 'stop' or result.tool_calls:
            raise ValueError('generator model completion did not finish')
        return result.text
    return complete


class AgentEditor:
    implementation_id = 'workspace-editor-v1'

    def __init__(self, config, artifacts, components, *, max_tool_calls=48, max_turns=12, instructions=None, page_characters=12000, projection='granted-full', access_mode='search'):
        self.config, self.artifacts, self.components = config, artifacts, components
        self.max_tool_calls = max_tool_calls
        self.instructions = instructions or EditorInstructions()
        self.workspace_session = WorkspaceSession(config, artifacts, max_tool_calls=max_tool_calls, max_turns=max_turns,
                                                  page_characters=page_characters, projection=projection, access_mode=access_mode)

    async def session(self, mission, workspace, services, *, writable=True, submit=None):
        return await self.workspace_session.session(mission, workspace, services,
            writable=writable, system=self.instructions.system, submit=submit)

    async def edit(self, stage, request, services):
        workspace = EvidenceWorkspace.build(request, self.artifacts, record=services.record)
        mission = getattr(self.instructions, request.scope) if stage == 'propose' else self.instructions.compose
        mission += ('\nAfter editing return only JSON {"reasons":[{"component_id":"...",'
            '"explanation":"...","evidence_ids":["run-id"]}]}. Each changed component needs a supplied run ID; no changes is valid.')
        mission += '\nUser guidance: ' + request.plan.direction
        mission += '\nPrefer submit_candidate to finish without a prose/JSON handoff. Search large evidence before reading selected pages.'
        mission += '\nRead execution metadata or relevant execution pages before citing a run. Listing paths alone does not supply evidence.'
        sealed = None
        def seal(value):
            nonlocal sealed
            sealed = submission(value, workspace, request, self.components)
        for attempt in range(2):
            response = ''
            try:
                response = await self.session(mission, workspace, services, submit=seal)
                return sealed if sealed is not None else submission(response, workspace, request, self.components)
            except EvidenceUnavailable as exc:
                services.record('editor-evidence-unavailable', attempt=attempt + 1)
                mission = 'Recover evidence access before proposing changes. Read context/executions.json and available execution resources. Cite only evidence successfully supplied. Retain the baseline if necessary evidence is unavailable.'
            except (ValueError, TypeError, KeyError) as exc:
                services.record('editor-invalid', attempt=attempt + 1, reason=str(exc))
                if not workspace.access.supplied:
                    mission = 'This editing stage did not finish with usable evidence. Inspect context/executions.json and recover access before editing; retain the baseline if evidence remains unavailable.'
                    continue
                workspace = workspace.repair_view(response, str(exc), workspace.access.supplied)
                mission = ('Repair only the existing candidate and submission. Previously supplied evidence remains eligible; '
                    'do not restart investigation. Read context/repair.json and context/submission.txt, inspect '
                    'the current harness files, then submit_candidate or return only the required reasons JSON.')
        services.record('editor-fallback', baseline_id=request.baseline.snapshot_id)
        return CandidateBundle(request.plan.parent, request.baseline, request.baseline, request.plan.generator_id)

