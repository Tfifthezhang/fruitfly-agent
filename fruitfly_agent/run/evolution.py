"""Supported composition entry for the capability-injected evolution host."""
from .improvement.evolution import RunEvolutionHost as EvolutionHost
from dataclasses import replace


class RunEvolutionHost(EvolutionHost):
    def __init__(self, application, factory, *, policy_id, verify, request):
        async def propose(direction):
            preview = application.workflow_preview(replace(request, direction=direction, scope='persistent'))
            return await application.improve(direction, preview_token=preview.preview_token)
        super().__init__(
            workspace=factory.cwd, manifest=lambda: application.runtime_manifest,
            propose=propose, read_candidate=factory.candidate_store.read,
            read_artifact=factory.artifact_store.read_text,
            prepare_candidate=factory.prepare_candidate, activate=application.activate_runtime,
            policy_id=policy_id, verify=verify,
        )
