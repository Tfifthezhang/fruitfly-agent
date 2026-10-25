"""Independent services and registered terminal commands use public contracts."""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, AsyncMock

from fruitfly_agent.interactive import AgentApplication, ApplicationState
from fruitfly_agent.interactive.contracts.candidates import CandidateView
from fruitfly_agent.interactive.contracts.commands import CommandResult, InteractiveCommand
from fruitfly_agent.interactive.contracts.improvement import ImprovementPreview
from fruitfly_agent.interactive.contracts.task_packs import TaskPackView
from fruitfly_agent.interactive.terminal import TerminalFrontend, TerminalCommandRegistry, TerminalBindings, ImprovementClients
from fruitfly_agent.interactive.terminal.features.configuration.command import configuration_handler
from tests.support.application import _Factory, offline_session
from tests.support.faux_provider import FauxProvider
from tests.support.terminal import ScriptedLines


class ExtensionTests(unittest.IsolatedAsyncioTestCase):
    async def app(self, **services):
        provider = FauxProvider()
        session = offline_session(provider=provider)

        class Factory(_Factory):
            async def open(self, **options):
                handle = await super().open(**options)
                for name, service in services.items():
                    setattr(handle, name, service)
                return handle

        app = AgentApplication(Factory([session]))
        await app.start()
        self.addAsyncCleanup(app.close)
        return app, provider

    async def test_task_materials_work_without_search_or_candidates(self):
        saved = []
        pack = TaskPackView("pack", "Corrections", "hash", 0, 0, 0, True)

        class Materials:
            def task_packs(self):
                return (pack,)
            def task_pack_holdout(self, pack_id):
                return ()
            def save_training_task(self, pack_id, input, expected, **options):
                saved.append((pack_id, input, expected, options))
                return replace(pack, train_count=1)

        app, provider = await self.app(task_packs=Materials())
        provider.respond_text("wrong")
        await app.submit("question")
        before = app.conversation()
        task = app.correction_tasks()[0]
        result = app.save_training_task(task.task_id, "pack", "question", "correct")
        self.assertTrue(app.task_packs_available)
        self.assertEqual(1, result.train_count)
        self.assertEqual(before, app.conversation())
        self.assertEqual(1, len(provider.calls))
        self.assertEqual(task.task_id, saved[0][3]["source"]["message_id"])
        self.assertEqual(app.runtime_manifest["digest"], saved[0][3]["source"]["parent_manifest"])
        self.assertEqual((), app.candidates())
        with self.assertRaisesRegex(RuntimeError, "no improvement service"):
            app.workflow_preview(None)

    async def test_candidate_review_works_without_improvement(self):
        view = CandidateView("candidate", "proposed", "custom", "text", "artifact", "improve", "parent")
        actions = []

        class Candidates:
            def candidates(self): return (view,)
            def candidate_notice(self): return ()
            def acknowledge_candidate_notice(self, ids): pass
            def candidate_detail(self, candidate_id): return view, "change"
            def candidate_action(self, manifest, candidate_id, action):
                actions.append((manifest["digest"], candidate_id, action))
                return replace(view, status="reviewed")

        app, provider = await self.app(candidates=Candidates())
        self.assertEqual((view,), app.candidates())
        self.assertEqual("reviewed", app.candidate_action("candidate", "review").status)
        self.assertEqual([(app.runtime_manifest["digest"], "candidate", "review")], actions)
        self.assertEqual([], provider.calls)

    async def test_search_only_service_obeys_application_exclusion_and_cancellation(self):
        entered = asyncio.Event()

        class Search:
            def improvement_preview(self, manifest, **options):
                return ImprovementPreview("custom", "Custom", "offline")
            async def improve(self, manifest, direction, **options):
                entered.set()
                await asyncio.Event().wait()
                return ()
            def cancel_improvement(self): return True

        app, provider = await self.app(improvement=Search())
        task = app.start_improvement("improve")
        await entered.wait()
        self.assertEqual(ApplicationState.IMPROVING, app.state)
        self.assertTrue(TerminalBindings.from_session(app).busy())
        with self.assertRaisesRegex(RuntimeError, "finish.*active work"):
            await app.apply_configuration()
        with self.assertRaisesRegex(RuntimeError, "cannot queue"):
            app.enqueue("next")
        with self.assertRaisesRegex(RuntimeError, "finish active work"):
            app.candidate_action("candidate", "review")
        self.assertTrue(app.cancel())
        with self.assertRaises(asyncio.CancelledError):
            await task
        await app.wait_for_improvement()
        self.assertEqual(ApplicationState.IDLE, app.state)
        self.assertEqual("cancelled", app.improvement_progress.status)
        self.assertEqual([], provider.calls)

    async def test_cancel_before_job_starts_restores_application_and_allows_next_job(self):
        calls = []

        class Search:
            async def improve(self, manifest, direction, **options):
                calls.append(direction)
                return ()
            def cancel_improvement(self): return True

        app, _ = await self.app(improvement=Search())
        task = app.start_improvement("first")
        app.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await app.wait_for_improvement()
        self.assertEqual(ApplicationState.IDLE, app.state)
        await app.improve("second")
        self.assertEqual(["second"], calls)
        self.assertEqual("completed", app.improvement_progress.status)

    async def test_async_command_extension_does_not_submit_to_model(self):
        app, provider = await self.app()
        calls = []

        async def inspect(command):
            await asyncio.sleep(0)
            calls.append(command.arguments)
            return CommandResult(text="extension result\n")

        output = io.StringIO()
        frontend = TerminalFrontend(
            app, input_stream=io.StringIO(), output_stream=output,
            line_editor=ScriptedLines("/inspect detail", "/exit"),
            command_handlers={"inspect": inspect},
        )
        self.assertEqual(0, await frontend.run())
        self.assertEqual([("detail",)], calls)
        self.assertIn("extension result", output.getvalue())
        self.assertEqual([], provider.calls)

    async def test_registry_checks_duplicates_names_and_results(self):
        registry = TerminalCommandRegistry({"custom": lambda command: CommandResult(text="first")})
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register("custom", lambda command: CommandResult())
        for name in ("", "UPPER", "two words", "a/b"):
            with self.assertRaises(ValueError):
                registry.register(name, lambda command: CommandResult())
        registry.register("custom", lambda command: CommandResult(text="replacement"), replace=True)
        self.assertEqual("replacement", (await registry.execute(InteractiveCommand("custom"))).text)
        self.assertIsNone(await registry.execute(InteractiveCommand("missing")))
        registry.register("bad", lambda command: "wrong type")
        with self.assertRaisesRegex(TypeError, "CommandResult"):
            await registry.execute(InteractiveCommand("bad"))

    async def test_configuration_flow_restores_menu_and_reports_apply_failure(self):
        lifecycle = []

        @contextmanager
        def scope():
            lifecycle.append("lend")
            try:
                yield
            finally:
                lifecycle.append("restore")

        async def fail():
            raise RuntimeError("replacement failed")

        from tests.support.configuration import MockConfiguration
        controller = MockConfiguration(model="offline")
        handler = configuration_handler(
            configuration=lambda: controller, status=lambda: offline_session().status,
            busy=lambda: False, apply_configuration=fail, menu_scope=scope,
            input_stream=io.StringIO(), output_stream=io.StringIO(),
            line_editor=lambda: ScriptedLines("3", "space", "back", "back", "1"),
            write=lambda text: None, welcome=lambda status: None,
        )
        result = await handler(InteractiveCommand("config"))
        self.assertIn("saved but not applied", result.text)
        self.assertIn("replacement failed", result.text)
        self.assertTrue(controller.saved)
        self.assertEqual(["lend", "restore"], lifecycle)

    async def test_configuration_save_only_does_not_apply_or_exit_the_conversation(self):
        from tests.support.configuration import MockConfiguration
        app, provider = await self.app()
        apply_settings = AsyncMock()
        bindings = replace(TerminalBindings.from_session(app), apply_configuration=apply_settings)
        controller = MockConfiguration(model='offline')
        output = io.StringIO()
        frontend = TerminalFrontend(app, bindings=bindings, configuration=controller,
            output_stream=output, line_editor=ScriptedLines('/config', '3', 'space', 'back', 'back', '2', '/status', '/exit'))
        await frontend.run()
        apply_settings.assert_not_awaited()
        self.assertTrue(controller.saved)
        self.assertIn('configuration saved; active runtime unchanged', output.getvalue())
        self.assertIn('state: idle', output.getvalue())
        self.assertEqual([], provider.calls)

    async def test_explicit_bindings_replace_optional_capability_discovery(self):
        app, provider = await self.app()
        cancelled = []
        bindings = replace(TerminalBindings.from_session(app), cancel=lambda: cancelled.append(True) or False)
        frontend = TerminalFrontend(
            app, bindings=bindings, input_stream=io.StringIO(), output_stream=io.StringIO(),
            line_editor=ScriptedLines("/cancel", "/exit"),
        )
        await frontend.run()
        self.assertEqual([True, True], cancelled)
        self.assertEqual([], provider.calls)

    async def test_menu_accepts_distinct_feature_clients(self):
        from tests.support.improvement_ui import configuration
        workflow = SimpleNamespace(workflow_configuration=configuration, workflow_preview=Mock())
        clients = ImprovementClients(workflow=workflow, candidates=SimpleNamespace(candidates=lambda: ()))
        provider = FauxProvider()
        output = io.StringIO()
        frontend = TerminalFrontend(offline_session(provider=provider), improvement_clients=clients,
            input_stream=io.StringIO(), output_stream=output,
            line_editor=ScriptedLines('/improvement', 'q', '/exit'))
        await frontend.run()
        self.assertIn('Component improvement', output.getvalue())
        self.assertIn('Input files', output.getvalue())
        self.assertIn('Start improvement', output.getvalue())
        self.assertNotIn('Editable components', output.getvalue())
        self.assertNotIn('Candidate generator', output.getvalue())
        workflow.workflow_preview.assert_not_called()
        self.assertEqual(provider.calls, [])

    async def test_previous_job_completion_cannot_reset_new_job_state(self):
        second_started, release = asyncio.Event(), asyncio.Event()
        tasks = []
        app = None

        class Search:
            async def improve(self, manifest, direction, **options):
                if direction == "first":
                    asyncio.get_running_loop().call_soon(
                        lambda: tasks.append(app.start_improvement("second"))
                    )
                    return ()
                second_started.set()
                await release.wait()
                return ()
            def cancel_improvement(self): return True

        app, _ = await self.app(improvement=Search())
        await app.improve("first")
        await second_started.wait()
        try:
            self.assertEqual(ApplicationState.IMPROVING, app.state)
            self.assertEqual("running", app.improvement_progress.status)
            self.assertEqual(2, app.improvement_progress.sequence)
        finally:
            release.set()
            await tasks[0]
        self.assertEqual(ApplicationState.IDLE, app.state)
