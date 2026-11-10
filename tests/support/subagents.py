"""Offline independent child runtime factory with explicit lifecycle observations."""
from pathlib import Path
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.session import Session
from fruitfly_agent.lab.catalog import PreparedAgentRuntime
from fruitfly_agent.run.storage.artifacts import DataArtifactStore
from fruitfly_agent.lab.agents.subagent.storage import SubagentStore
from fruitfly_agent.lab.agents.subagent.service import SubagentService
from tests.support.faux_provider import FauxProvider

class ChildFixture:
    def __init__(self, root):
        self.root = Path(root)
        self.providers = []
        self.sessions = []
        self.started = 0
        self.closed = 0
        self.provider = lambda request: self.answer()
        self.store = SubagentStore(self.root / 'children', DataArtifactStore(self.root / 'artifacts'))

    def answer(self):
        provider = FauxProvider()
        provider.respond_text('child result')
        return provider

    async def prepare(self, request):
        session = Session(self.root / request.identity.agent_id / 'session.jsonl')
        provider = self.provider(request)
        self.providers.append(provider)
        self.sessions.append(session)
        async def start():
            self.started += 1
        async def close():
            self.closed += 1
            session.close()
        return PreparedAgentRuntime(AgentLoopConfig(provider=provider, session=session, model='child-model'),
            None, {'model_profile': 'child'}, start, close)

    def service(self, **kwargs):
        return SubagentService(self.prepare, self.store, **kwargs)
