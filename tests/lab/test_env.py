"""Lab LocalEnv Result discipline + shell semantics."""

import tempfile
import unittest
from pathlib import Path

from fruitfly_agent.core.env import ExecOptions
from fruitfly_agent.core.errors import Result
from fruitfly_agent.lab.environment import LocalEnv


class TestEnv(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = LocalEnv(cwd=str(self.root))

    def tearDown(self):
        self.tmp.cleanup()

    async def test_write_creates_parents(self):
        result = self.env.write_file("a/b/c.txt", "hello")
        self.assertTrue(result.is_ok)
        self.assertEqual((self.root / "a/b/c.txt").read_text(), "hello")

    async def test_read_missing_returns_err(self):
        result = self.env.read_text_file("nope.txt")
        self.assertFalse(result.is_ok)

    async def test_absolute_and_join(self):
        self.assertTrue(self.env.absolute_path("x").is_ok)
        joined = self.env.join_path([str(self.root), "y"])
        self.assertTrue(joined.is_ok)
        self.assertEqual(joined.unwrap(), str(self.root / "y"))

    async def test_file_info_and_list(self):
        self.env.write_file("f.txt", "x")
        info = self.env.file_info("f.txt")
        self.assertTrue(info.is_ok)
        self.assertEqual(info.unwrap().kind, "file")
        listing = self.env.list_dir(".")
        self.assertTrue(listing.is_ok)
        self.assertEqual([f.name for f in listing.unwrap()], ["f.txt"])

    async def test_exec_success(self):
        result = await self.env.exec("echo hello")
        self.assertTrue(result.is_ok, result.error)
        r = result.unwrap()
        self.assertEqual(r.exit_code, 0)
        self.assertIn("hello", r.stdout)

    async def test_exec_timeout_kills_process_group(self):
        # A grandchild: timeout must kill the whole group, not just the shell.
        result = await self.env.exec(
            "sh -c 'sleep 30 & sleep 30'",
            options=ExecOptions(timeout_seconds=1),
        )
        self.assertTrue(result.is_ok)
        r = result.unwrap()
        self.assertTrue(r.cancelled)

    async def test_exec_env_inherit(self):
        result = await self.env.exec(
            "echo $FRUITFLY_TEST_MARKER", options=ExecOptions(env={"FRUITFLY_TEST_MARKER": "hello"})
        )
        self.assertTrue(result.is_ok, result.error)
        self.assertIn("hello", result.unwrap().stdout)

    async def test_remove_recursive(self):
        self.env.write_file("d/e.txt", "x")
        result = self.env.remove("d", recursive=True)
        self.assertTrue(result.is_ok)
        self.assertFalse((self.root / "d").exists())


if __name__ == "__main__":
    unittest.main()

class GuardedEnvironmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_workspace_state_allowed_and_secrets_and_symlink_aliases_denied(self):
        from fruitfly_agent.lab.environment.permissions import PermissionPolicy, PermissionAuthorizer
        from fruitfly_agent.lab.environment.guarded import GuardedEnv
        from fruitfly_agent.core.tool_runtime.authorization import AuthorizationRequest, ToolPermission
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / 'workspace'
            workspace.mkdir()
            secret = workspace / '.env'
            secret.write_text('offline placeholder')
            (workspace / 'alias').symlink_to(secret)
            (workspace / 'hardlink').hardlink_to(secret)
            authorizer = PermissionAuthorizer(PermissionPolicy(workspace, sensitive_paths=(secret,)))
            env = GuardedEnv(LocalEnv(str(workspace)), authorizer)
            self.assertTrue(env.write_file('.fruitfly/learning/state.json', '{}').is_ok)
            self.assertTrue(env.read_text_file('.fruitfly/learning/state.json').is_ok)
            self.assertTrue(env.create_temp_file().is_ok)
            for path in ('.env', 'alias', 'hardlink'):
                self.assertFalse(env.read_text_file(path).is_ok)
                self.assertFalse(env.write_file(path, 'replace').is_ok)
            request = AuthorizationRequest('secret', 'read', {'path': '.env'}, ToolPermission('read', ('path',)))
            async with authorizer.authorize(request) as decision:
                self.assertFalse(decision.allowed)

    async def test_external_confirmation_is_exact_and_symlink_swap_is_rechecked(self):
        from fruitfly_agent.lab.environment.permissions import PermissionPolicy, PermissionAuthorizer
        from fruitfly_agent.lab.environment.guarded import GuardedEnv
        from fruitfly_agent.core.tool_runtime.authorization import AuthorizationRequest, ToolPermission
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / 'workspace'
            workspace.mkdir()
            target = root / 'allowed.txt'
            target.write_text('allowed')
            other = root / 'other.txt'
            other.write_text('other')
            link = workspace / 'link'
            link.symlink_to(target)
            prompts = []
            async def confirm(prompt, signal):
                prompts.append(prompt)
                return 'once'
            authorizer = PermissionAuthorizer(PermissionPolicy(workspace), confirm=confirm)
            env = GuardedEnv(LocalEnv(str(workspace)), authorizer)
            request = AuthorizationRequest('read', 'read', {'path': str(link)}, ToolPermission('read', ('path',)))
            self.assertFalse(env.read_text_file(str(target)).is_ok)
            async with authorizer.authorize(request) as decision:
                self.assertTrue(decision.allowed)
                self.assertEqual('allowed', env.read_text_file(str(link)).unwrap())
                self.assertFalse(env.read_text_file(str(other)).is_ok)
                import asyncio
                release = asyncio.Event()
                async def delayed():
                    await release.wait()
                    return env.read_text_file(str(target))
                background = asyncio.create_task(delayed())
                link.unlink()
                link.symlink_to(other)
                self.assertFalse(env.read_text_file(str(link)).is_ok)
            release.set()
            self.assertFalse((await background).is_ok)
            self.assertFalse(env.read_text_file(str(target)).is_ok)
            self.assertEqual((str(target.resolve()),), prompts[0].targets)

    async def test_shell_requires_approval_and_receives_only_explicit_environment(self):
        from fruitfly_agent.lab.environment.permissions import PermissionPolicy, PermissionAuthorizer
        from fruitfly_agent.lab.environment.guarded import GuardedEnv
        from fruitfly_agent.core.tool_runtime.authorization import AuthorizationRequest, ToolPermission
        from fruitfly_agent.core.env import ExecOptions
        from pathlib import Path
        from unittest.mock import AsyncMock, patch
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            async def confirm(prompt, signal):
                return 'once'
            authorizer = PermissionAuthorizer(PermissionPolicy(Path(directory)), confirm=confirm)
            backend = LocalEnv(directory)
            backend.exec = AsyncMock(return_value=Result.success(None))
            env = GuardedEnv(backend, authorizer, process_environment={'PATH': '/usr/bin:/bin'})
            self.assertFalse((await env.exec('echo ok')).is_ok)
            request = AuthorizationRequest('exec', 'bash', {'command': 'echo ok'}, ToolPermission('execute'))
            with patch.dict('os.environ', {'TEST_PROVIDER_KEY': 'offline-placeholder'}):
                async with authorizer.authorize(request) as decision:
                    self.assertTrue(decision.allowed)
                    await env.exec('echo ok', ExecOptions())
                    self.assertFalse((await env.exec('different command')).is_ok)
                    self.assertFalse((await env.exec('echo ok', ExecOptions(cwd='/'))).is_ok)
            options = backend.exec.call_args.args[1]
            self.assertFalse(options.inherit_env)
            self.assertEqual({'PATH': '/usr/bin:/bin'}, options.env)
            self.assertFalse((await env.exec('echo again')).is_ok)
