"""Application lifecycle, queueing, and runtime replacement behavior."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from fruitfly_agent.core.data_model import AgentLoopResult
from fruitfly_agent.interactive import (
    AgentApplication,
    ApplicationState,
    ResumableSession,
    RuntimeHandle,
)
from tests.support.application import _Factory, offline_session
from fruitfly_agent.interactive.optimization import CandidateView


class AgentApplicationTest(unittest.IsolatedAsyncioTestCase):
    async def _switch_fixture(self, *, activate=None, retire=None, start=None):
        lifecycle = []
        first = offline_session(model='first', session_path='first.jsonl')
        second = offline_session(model='second', session_path='second.jsonl')

        class Component:
            async def start(self):
                lifecycle.append("start:second")
                if start is not None:
                    await start()

            def close(self):
                lifecycle.append("close:second")

        def close_first():
            lifecycle.append("close:first")
            if retire is not None:
                retire()

        candidate = RuntimeHandle(
            second, {"digest": "candidate"}, {"component": Component()},
            activate_callback=activate,
        )
        view = CandidateView("candidate", "proposed", "custom", "text", "artifact", "improve", "sha256:test")

        class Service:
            def candidates(self):
                return (view,)

            async def prepare_candidate(self, manifest, candidate_id):
                return candidate

        class Factory(_Factory):
            async def open(self, *, resume, session_path):
                if self.opened:
                    return candidate
                handle = await super().open(resume=resume, session_path=session_path)
                handle.close_callback = close_first
                handle.optimization = handle.candidate_activation = Service()
                return handle

        app = AgentApplication(Factory([first]))
        await app.start()
        self.addAsyncCleanup(app.close)
        return app, candidate, lifecycle

    async def _switch(self, app, candidate, operation):
        if operation == "rebuild":
            await app.rebuild()
        elif operation == "resume":
            await app.resume("second.jsonl")
        elif operation == "adopt":
            await app.adopt_candidate("candidate")
        else:
            await app.activate_runtime(candidate, expected_manifest_digest="sha256:test")

    async def test_replacement_activation_failure_preserves_incumbent(self):
        for operation in ("rebuild", "resume", "adopt", "activate"):
            with self.subTest(operation=operation):
                def fail():
                    raise RuntimeError("activation failed")

                app, candidate, lifecycle = await self._switch_fixture(activate=fail)
                with self.assertRaisesRegex(RuntimeError, "activation failed"):
                    await self._switch(app, candidate, operation)
                self.assertEqual("first", app.status.model)
                self.assertEqual(ApplicationState.IDLE, app.state)
                self.assertEqual(["start:second", "close:second"], lifecycle)
                await app.close()

    async def test_replacement_retirement_failure_preserves_successful_switch(self):
        for operation in ("rebuild", "resume", "adopt", "activate"):
            with self.subTest(operation=operation):
                def fail():
                    raise RuntimeError("retirement failed")

                app, candidate, lifecycle = await self._switch_fixture(retire=fail)
                await self._switch(app, candidate, operation)
                self.assertEqual("second", app.status.model)
                self.assertEqual(ApplicationState.IDLE, app.state)
                self.assertIn("retirement failed", str(app.last_error))
                self.assertEqual(["start:second", "close:first"], lifecycle)
                await app.close()

    async def test_replacement_start_cancellation_preserves_incumbent(self):
        for operation in ("rebuild", "resume", "adopt", "activate"):
            with self.subTest(operation=operation):
                entered = asyncio.Event()

                async def wait():
                    entered.set()
                    await asyncio.Event().wait()

                app, candidate, lifecycle = await self._switch_fixture(start=wait)
                switching = asyncio.create_task(self._switch(app, candidate, operation))
                await asyncio.wait_for(entered.wait(), timeout=1)
                switching.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await switching
                self.assertEqual("first", app.status.model)
                self.assertEqual(ApplicationState.IDLE, app.state)
                self.assertEqual(["start:second", "close:second"], lifecycle)
                await app.close()

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

        session = offline_session(model='offline', run_loop=run)
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
        first = offline_session(model='first', session_path='first.jsonl')
        second = offline_session(model='second', session_path='second.jsonl')
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

        first = offline_session(model='first', run_loop=run)
        second = offline_session(model='second')

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
        first = offline_session(model='first')
        second = offline_session(model='second')

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

        first = offline_session(model='first', session_path='first.jsonl')
        second = offline_session(model='second', session_path='second.jsonl')

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
        first = offline_session(model='first', session_path='first.jsonl')

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
        first = offline_session(model='first', session_path='first.jsonl')
        second = offline_session(model='second', session_path='second.jsonl')

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

        session = offline_session(model='offline')
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
            offline_session(model='offline'),
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
