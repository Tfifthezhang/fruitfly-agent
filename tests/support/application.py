"""RuntimeFactory and task-application fixtures with offline providers."""
from pathlib import Path
from unittest.mock import Mock
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.interactive import AgentApplication, InteractiveSession, ResumableSession, RuntimeHandle
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.faux_provider import FauxProvider
from tests.support.materials import _write_models


def offline_session(*, provider=None, model="offline-model", **kwargs):
    return InteractiveSession(
        AgentLoopConfig(provider=provider if provider is not None else FauxProvider(), model=model),
        **kwargs,
    )


class _Factory:
    def __init__(self, sessions: list[InteractiveSession]) -> None:
        self.configuration = Mock()
        self.sessions = iter(sessions)
        self.opened: list[tuple[bool, Path | None]] = []
        self.reloads = 0
        self.candidates: tuple[ResumableSession, ...] = ()

    async def open(self, *, resume: bool, session_path: Path | None):
        self.opened.append((resume, session_path))
        return RuntimeHandle(
            next(self.sessions),
            {"digest": "sha256:test", "open": len(self.opened)},
        )

    def reload_configuration(self) -> None:
        self.reloads += 1

    def new_session_path(self) -> Path:
        return Path(f"session-{len(self.opened) + 1}.jsonl")

    def resumable_sessions(self, *, current_path, manifest_digest):
        self.discovery = (current_path, manifest_digest)
        return self.candidates

async def open_task_app(self, root, algorithm=None):
    _write_models(root)
    provider = FauxProvider()
    registry = Mock()
    registry.create.return_value = provider
    factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=registry)
    if algorithm:
        factory.configuration.set_mechanism(algorithm, enabled=True)
        factory.configuration.save()
        factory.reload_configuration()
    app = AgentApplication(factory)
    await app.start()
    self.addAsyncCleanup(app.close)
    return app, factory, provider
