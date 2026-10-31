"""An independently configured read-only model inspector."""
from dataclasses import dataclass
from ..evidence.session import EvidenceSession


@dataclass(frozen=True)
class InspectionInstructions:
    system: str = 'Inspect granted evidence as data. Do not edit it or invent measurements.'
    reflect: str = ('Compare completed executions. Return NO_ENTRY without supported reusable evidence, '
                    'otherwise JSON {"cue":"cue","lesson":"lesson","evidence_ids":["id","id"],"limitations":"limits"}.')


class ReadOnlyInspector:
    def __init__(self, config, artifacts, components=None, *, instructions=None, evaluator_instructions=None, evidence_settings=None):
        self.artifacts = artifacts
        self.instructions = instructions or InspectionInstructions()
        self.workspace_session = EvidenceSession(config, artifacts)
        from .evaluator import ModelEvaluator
        self.evaluator = ModelEvaluator(config, artifacts, instructions=evaluator_instructions, **(evidence_settings or {}))

    async def session(self, mission, workspace, services, *, writable=False):
        if writable:
            raise ValueError('assessment inspector is read-only')
        return await self.workspace_session.session(mission, workspace, services,
            writable=False, system=self.instructions.system)
