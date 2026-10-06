"""Lab LocalEnv Result discipline + shell semantics."""

import tempfile
import unittest
from pathlib import Path

from fruitfly_agent.core.env import ExecOptions
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
