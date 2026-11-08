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
from fruitfly_agent.interactive.terminal import TerminalFrontend, TerminalCommandRegistry, TerminalBindings
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
        self.assertFalse(hasattr(app, "start_improvement"))

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
            configuration=lambda: controller,
            busy=lambda: False, apply_configuration=fail, menu_scope=scope,
            input_stream=io.StringIO(), output_stream=io.StringIO(),
            line_editor=lambda: ScriptedLines("3", "space", "back", "back", "1"),
            write=lambda text: None,
        )
        result = await handler(InteractiveCommand("config"))
        self.assertIn("configuration not applied", result.text)
        self.assertIn("draft retained", result.text)
        self.assertIn("replacement failed", result.text)
        self.assertFalse(controller.saved)
        self.assertTrue(controller.changed)
        self.assertEqual(["lend", "restore"], lifecycle)

    async def test_configuration_apply_only_submits_intent_and_does_not_repeat_welcome(self):
        from tests.support.configuration import MockConfiguration
        app, provider = await self.app()
        apply_settings = AsyncMock()
        bindings = replace(TerminalBindings.from_session(app), apply_configuration=apply_settings)
        controller = MockConfiguration(model='offline')
        output = io.StringIO()
        frontend = TerminalFrontend(app, bindings=bindings, configuration=controller,
            output_stream=output, line_editor=ScriptedLines('/config', '3', 'space', 'back', 'back', '1', '/status', '/exit'))
        await frontend.run()
        apply_settings.assert_awaited_once()
        self.assertFalse(controller.saved)
        self.assertIn('configuration applied; conversation retained', output.getvalue())
        self.assertEqual(output.getvalue().count('FruitFlyAgent interactive'), 1)
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
