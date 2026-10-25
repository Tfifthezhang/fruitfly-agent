"""An independently configured read-only model inspector."""
from dataclasses import dataclass
from ..evidence.session import WorkspaceSession


@dataclass(frozen=True)
class InspectionInstructions:
    system: str = 'Inspect granted evidence as data. Do not edit it or invent measurements.'
    select: str = ('Choose an existing anonymous deliverable from task evidence. Return NO_CLEAR_CHOICE '
                   'if indistinguishable, otherwise JSON {"choice":"id","reason":"reason"}.')
    reflect: str = ('Compare completed executions. Return NO_ENTRY without supported reusable evidence, '
                    'otherwise JSON {"cue":"cue","lesson":"lesson","evidence_ids":["id","id"],"limitations":"limits"}.')


class ReadOnlyInspector:
    def __init__(self, config, artifacts, components=None, *, instructions=None):
        self.artifacts = artifacts
        self.instructions = instructions or InspectionInstructions()
        self.workspace_session = WorkspaceSession(config, artifacts)

    async def session(self, mission, workspace, services, *, writable=False):
        if writable:
            raise ValueError('assessment inspector is read-only')
        return await self.workspace_session.session(mission, workspace, services,
            writable=False, system=self.instructions.system)
