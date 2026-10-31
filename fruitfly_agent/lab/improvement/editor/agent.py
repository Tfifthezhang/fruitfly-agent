"""The default tool-using editor; all algorithms share the generator protocol."""
from __future__ import annotations

import json

from fruitfly_agent.core.data_model import UserMessage, ProviderView
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from fruitfly_agent.improvement.contracts.failures import IntegrityError
from ..evidence import EvidenceWorkspace
from ..evidence.access import EvidenceUnavailable
from .instructions import EditorInstructions
from ..evidence.session import EvidenceSession
from .submission import submission
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash


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

    def __init__(self, config, artifacts, components, *, instructions=None, page_characters=12000, reader_factory=None):
        self.config, self.artifacts, self.components = config, artifacts, components
        self.instructions = instructions or EditorInstructions()
        self.workspace_session = EvidenceSession(config, artifacts, page_characters=page_characters, reader_factory=reader_factory)

    async def session(self, mission, workspace, services, *, writable=True, submit=None):
        return await self.workspace_session.session(mission, workspace, services,
            writable=writable, system=self.instructions.system, submit=submit)

    async def edit(self, stage, request, services):
        return await services.operation(self._edit(stage,request,services),stage='editor')

    async def _edit(self,stage,request,services):
        workspace = EvidenceWorkspace.build(request, self.artifacts, record=services.record)
        descriptions = self.components.descriptions(request.plan.component_ids, snapshot=request.baseline)
        description_text = canonical_json(descriptions)
        summary=[]
        for name,value in descriptions.items():
            details=canonical_json(value).encode()
            path='context/components/'+name+'.json'
            workspace.references[path]=self.artifacts.put(details)
            summary.append({'component_id':name,'role':value['role'],'fields':[f['path'] for f in value['fields']], 'details_path':path})
        workspace.files['context/components.json']=canonical_json(summary).encode()
        services.record('component-descriptions',identity=content_hash(description_text),
            conditions_id=request.plan.conditions_id,baseline_id=request.baseline.snapshot_id,
            artifact_id=self.artifacts.put(description_text.encode()))
        mission = getattr(self.instructions, request.scope) if stage == 'propose' else self.instructions.compose
        mission += '\nUse list_targets and describe_target to load parameter semantics on demand. Read context/edit-grants.json for this experiment’s scope.'
        mission += ('\nAfter editing return only JSON {"reasons":[{"component_id":"...",'
            '"explanation":"...","expected_effect":"observable change and disconfirming evidence","evidence_ids":["run-id"]}]}. Each changed component needs a supplied run ID; no changes is valid.')
        mission += '\nUser guidance: ' + request.plan.direction
        mission += '\nPrefer submit_candidate to finish without a prose/JSON handoff. Search large evidence before reading selected pages.'
        mission += '\nRead execution metadata or relevant execution pages before citing a run. Listing paths alone does not supply evidence.'
        sealed = None
        def seal(value):
            nonlocal sealed
            sealed = submission(value, workspace, request, self.components)
        attempt = 0
        while True:
            services.check()
            attempt += 1
            response = ''
            try:
                response = await self.session(mission, workspace, services, submit=seal)
                return sealed if sealed is not None else submission(response, workspace, request, self.components)
            except IntegrityError:
                raise
            except EvidenceUnavailable as exc:
                services.record('editor-evidence-unavailable', attempt=attempt)
                mission = 'Recover evidence access before proposing changes. Read context/executions.json and available execution resources. Cite only evidence successfully supplied. Retain the baseline if necessary evidence is unavailable.'
            except (ValueError, TypeError, KeyError) as exc:
                services.record('editor-invalid', attempt=attempt, reason=str(exc))
                if not workspace.access.supplied:
                    mission = 'This editing stage did not finish with usable evidence. Inspect context/executions.json and recover access before editing; retain the baseline if evidence remains unavailable.'
                    continue
                workspace = workspace.repair_view(response, str(exc), workspace.access.supplied)
                mission = ('Repair only the existing candidate and submission. Previously supplied evidence remains eligible; '
                    'do not restart investigation. Read context/repair.json and context/submission.txt, inspect '
                    'the current harness files, then submit_candidate or return only the required reasons JSON.')
