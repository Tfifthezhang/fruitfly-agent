"""Cli behavior and failure contracts."""
from __future__ import annotations
import contextlib
import io
import unittest
from unittest.mock import patch
from fruitfly_agent.run import create_parser
from fruitfly_agent.run import cli
from tests.support.run import _args


class CliSurfaceTest(unittest.TestCase):
    def test_parser_keeps_only_stable_launch_and_profile_options(self) -> None:
        args = create_parser().parse_args(["do work", "--profile", "research"])

        self.assertEqual(args.task, "do work")
        self.assertEqual(args.profile, "research")
        self.assertFalse(args.resume)
        self.assertFalse(args.configure)
        self.assertFalse(args.approve_tools)
        self.assertFalse(
            any(
                hasattr(args, name)
                for name in ("provider", "model", "memory_profile", "models_file")
            )
        )

    def test_parser_supports_configuring_before_interactive_chat(self):
        self.assertTrue(create_parser().parse_args(['--configure']).configure)

    def test_feature_specific_legacy_flag_is_rejected(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            create_parser().parse_args(["--memory-profile", "obsolete"])


class CliRunTest(unittest.IsolatedAsyncioTestCase):
    async def test_tool_approval_flag_rejects_interactive_and_resumed_work(self):
        for args in (_args(approve_tools=True), _args(task="resume", resume=True, approve_tools=True)):
            with contextlib.redirect_stderr(io.StringIO()), patch.object(cli, "RunApplicationFactory") as factory:
                self.assertEqual(await cli.run_cli(args), 2)
                factory.assert_not_called()
