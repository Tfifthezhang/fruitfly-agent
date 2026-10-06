"""Application lifecycle, queueing, and runtime replacement behavior."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
import tempfile
from unittest.mock import Mock
from unittest.mock import patch

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AgentLoopResult
from fruitfly_agent.interactive import (
    AgentApplication,
    ApplicationState,
    InteractiveSession,
    ResumableSession,
    RuntimeHandle,
)
from tests.support.faux_provider import FauxProvider
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.application import _Factory




class AgentApplicationTest(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_queue_runs_serially_and_exposes_state(self) -> None:
        prompts: list[str] = []

        async def run(config, messages, *, signal, context_pipeline):
            prompts.append(messages[-1].content)
            await asyncio.sleep(0)
            return AgentLoopResult(
                messages=list(messages),
                stop_reason="stop",
                model=config.model,
            )

        session = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="offline"),
            run_loop=run,
        )
        application = AgentApplication(_Factory([session]))
        await application.start(session_path=Path("first.jsonl"))

        manifest = application.runtime_manifest
        self.assertEqual(manifest["digest"], "sha256:test")
        self.assertEqual(manifest["open"], 1)

        application.enqueue("one")
        application.enqueue("two")
        await application.wait_until_idle()

        self.assertEqual(prompts, ["one", "two"])
        self.assertEqual(application.state, ApplicationState.IDLE)
        self.assertEqual(application.pending_count, 0)
        await application.close()
        self.assertEqual(application.state, ApplicationState.CLOSED)

    async def test_rebuild_replaces_runtime_and_reloads_saved_configuration(self) -> None:
        first = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="first"),
            session_path="first.jsonl",
        )
        second = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="second"),
            session_path="second.jsonl",
        )
        factory = _Factory([first, second])
        application = AgentApplication(factory)
        await application.start(session_path=Path("first.jsonl"))

        await application.rebuild()

        self.assertEqual(factory.reloads, 1)
        self.assertEqual(application.status.model, "second")
        self.assertEqual(application.status.session_path, "second.jsonl")
        await application.close()

    async def test_rebuild_waits_for_direct_submission_before_closing_runtime(self) -> None:
        run_started = asyncio.Event()
        run_finished = asyncio.Event()
        lifecycle: list[str] = []

        async def run(config, messages, *, signal, context_pipeline):
            run_started.set()
            await signal.wait()
            lifecycle.append("run-finished")
            run_finished.set()
            return AgentLoopResult(
                messages=list(messages),
                stop_reason="aborted",
                model=config.model,
            )

        first = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="first"),
            run_loop=run,
        )
        second = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="second")
        )

        class Factory(_Factory):
            async def open(self, *, resume: bool, session_path: Path | None):
                handle = await super().open(resume=resume, session_path=session_path)
                if len(self.opened) == 1:
                    handle.close_callback = lambda: lifecycle.append("runtime-closed")
                return handle

        application = AgentApplication(Factory([first, second]))
        await application.start(session_path=Path("first.jsonl"))
        submission = asyncio.create_task(application.submit("hello"))
        await run_started.wait()

        await application.rebuild()
        await submission

        self.assertTrue(run_finished.is_set())
        self.assertEqual(lifecycle, ["run-finished", "runtime-closed"])
        self.assertEqual(application.state, ApplicationState.IDLE)
        self.assertEqual(application.status.model, "second")
        await application.close()

    async def test_rebuild_rejects_new_queue_items(self) -> None:
        close_started = asyncio.Event()
        allow_close = asyncio.Event()
        first = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="first")
        )
        second = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="second")
        )

        class Factory(_Factory):
            async def open(self, *, resume: bool, session_path: Path | None):
                handle = await super().open(resume=resume, session_path=session_path)
                if len(self.opened) == 1:
                    async def close_runtime() -> None:
                        close_started.set()
                        await allow_close.wait()

                    handle.close_callback = close_runtime
                return handle

        factory = Factory([first, second])
        application = AgentApplication(factory)
        await application.start(session_path=Path("first.jsonl"))

        rebuilding = asyncio.create_task(application.rebuild())
        await close_started.wait()
        with self.assertRaisesRegex(RuntimeError, "cannot queue while application"):
            application.enqueue("too late")

        allow_close.set()
        await rebuilding
        await application.close()

    async def test_resume_discovers_and_transactionally_switches_runtime(self) -> None:
        lifecycle: list[str] = []

        class Component:
            def __init__(self, name: str) -> None:
                self.name = name

            def start(self) -> None:
                lifecycle.append(f"start:{self.name}")

            def close(self) -> None:
                lifecycle.append(f"close:{self.name}")

        first = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="first"),
            session_path="first.jsonl",
        )
        second = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="second"),
            session_path="second.jsonl",
        )

        class Factory(_Factory):
            async def open(self, *, resume: bool, session_path: Path | None):
                handle = await super().open(
                    resume=resume,
                    session_path=session_path,
                )
                name = "first" if len(self.opened) == 1 else "second"
                handle.components = {name: Component(name)}
                return handle

        factory = Factory([first, second])
        factory.candidates = (
            ResumableSession(
                path="second.jsonl",
                modified_at=2.0,
                message_count=4,
                profile="default",
                model="second",
            ),
        )
        application = AgentApplication(factory)
        await application.start(session_path=Path("first.jsonl"))

        self.assertEqual(application.resumable_sessions(), factory.candidates)
        self.assertEqual(
            factory.discovery,
            (Path("first.jsonl"), "sha256:test"),
        )

        await application.resume("second.jsonl")

        self.assertEqual(application.state, ApplicationState.IDLE)
        self.assertEqual(application.status.model, "second")
        self.assertEqual(application.status.session_path, "second.jsonl")
        self.assertEqual(factory.opened[-1], (True, Path("second.jsonl")))
        self.assertEqual(
            lifecycle,
            ["start:first", "start:second", "close:first"],
        )
        await application.close()

    async def test_resume_failure_keeps_current_runtime_active(self) -> None:
        first = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="first"),
            session_path="first.jsonl",
        )

        class Factory(_Factory):
            async def open(self, *, resume: bool, session_path: Path | None):
                if resume:
                    raise ValueError("incompatible manifest")
                return await super().open(
                    resume=resume,
                    session_path=session_path,
                )

        application = AgentApplication(Factory([first]))
        await application.start(session_path=Path("first.jsonl"))

        with self.assertRaisesRegex(RuntimeError, "incompatible manifest"):
            await application.resume("second.jsonl")

        self.assertEqual(application.state, ApplicationState.IDLE)
        self.assertEqual(application.status.model, "first")
        await application.close()

    async def test_resume_start_failure_keeps_current_runtime_active(self) -> None:
        first = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="first"),
            session_path="first.jsonl",
        )
        second = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="second"),
            session_path="second.jsonl",
        )

        class BrokenComponent:
            def start(self) -> None:
                raise RuntimeError("component start failed")

        class Factory(_Factory):
            async def open(self, *, resume: bool, session_path: Path | None):
                handle = await super().open(
                    resume=resume,
                    session_path=session_path,
                )
                if resume:
                    handle.components = {"broken": BrokenComponent()}
                return handle

        application = AgentApplication(Factory([first, second]))
        await application.start(session_path=Path("first.jsonl"))

        with self.assertRaisesRegex(RuntimeError, "component start failed"):
            await application.resume("second.jsonl")

        self.assertEqual(application.state, ApplicationState.IDLE)
        self.assertEqual(application.status.model, "first")
        await application.close()


class RuntimeHandleTest(unittest.IsolatedAsyncioTestCase):
    async def test_components_start_health_and_close_in_reverse_order(self) -> None:
        calls: list[str] = []

        class Component:
            def __init__(self, name: str) -> None:
                self.name = name

            async def start(self):
                calls.append(f"start:{self.name}")

            def health(self):
                return f"healthy:{self.name}"

            async def close(self):
                calls.append(f"close:{self.name}")

        session = InteractiveSession(
            AgentLoopConfig(provider=FauxProvider(), model="offline")
        )
        handle = RuntimeHandle(
            session,
            {"digest": "test"},
            {"first": Component("first"), "second": Component("second")},
        )

        await handle.start()
        self.assertEqual(
            await handle.health(),
            {"first": "healthy:first", "second": "healthy:second"},
        )
        await handle.close()

        self.assertEqual(
            calls,
            ["start:first", "start:second", "close:second", "close:first"],
        )

    async def test_start_failure_closes_every_component_that_was_entered(self) -> None:
        calls: list[str] = []

        class Component:
            def __init__(self, name: str, *, fail: bool = False) -> None:
                self.name = name
                self.fail = fail

            def start(self):
                calls.append(f"start:{self.name}")
                if self.fail:
                    raise RuntimeError("boom")

            def close(self):
                calls.append(f"close:{self.name}")

        handle = RuntimeHandle(
            InteractiveSession(
                AgentLoopConfig(provider=FauxProvider(), model="offline")
            ),
            {"digest": "test"},
            {
                "first": Component("first"),
                "broken": Component("broken", fail=True),
            },
        )

        with self.assertRaisesRegex(RuntimeError, "boom"):
            await handle.start()

        self.assertEqual(
            calls,
            ["start:first", "start:broken", "close:broken", "close:first"],
        )



if __name__ == "__main__":
    unittest.main()
