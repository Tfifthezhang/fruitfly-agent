"""Lab builtin tool behavior: read/write/edit/bash (offline, real files)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fruitfly_agent.lab.environment import LocalEnv
from fruitfly_agent.core.tool_runtime import ToolCallContext
from fruitfly_agent.core.env import ExecResult
from fruitfly_agent.core.errors import Result
from fruitfly_agent.lab.tools.bash import create_bash_tool
from fruitfly_agent.lab.tools.edit import create_edit_tool
from fruitfly_agent.lab.tools.read import create_read_tool
from fruitfly_agent.lab.tools.write import create_write_tool


class ToolTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = LocalEnv(cwd=str(self.root))

    def tearDown(self):
        self.tmp.cleanup()

    def ctx(self, name, args, on_update=None):
        return ToolCallContext(
            tool_call_id="call_test", name=name, args=args, env=self.env, on_update=on_update
        )

    async def run_tool(self, tool, args, on_update=None):
        result = tool.execute(self.ctx(tool.name, args, on_update))
        if hasattr(result, "__await__"):
            return await result
        return result

    async def test_write_and_read_roundtrip(self):
        await self.run_tool(create_write_tool(), {"path": "x.txt", "content": "line1\nline2\nline3"})
        result = await self.run_tool(create_read_tool(), {"path": "x.txt"})
        self.assertIn("line1", result.content[0].text)
        self.assertIn("line3", result.content[0].text)

    async def test_write_reports_character_count_and_preserves_content(self):
        for content, count in (("", 0), ("hello", 5), ("ＡＢ\U0001f34e\ne\u0301", 6)):
            with self.subTest(content=content):
                result = await self.run_tool(
                    create_write_tool(), {"path": "count.txt", "content": content}
                )
                self.assertEqual(
                    result.content[0].text,
                    f"Successfully wrote {count} characters to count.txt",
                )
                self.assertEqual(
                    (self.root / "count.txt").read_text(encoding="utf-8"), content
                )

    async def test_read_offset_limit_hint(self):
        await self.run_tool(create_write_tool(), {"path": "y.txt", "content": "a\nb\nc\nd\ne"})
        result = await self.run_tool(create_read_tool(), {"path": "y.txt", "offset": 2, "limit": 2})
        text = result.content[0].text
        self.assertIn("b", text)
        self.assertIn("c", text)
        self.assertNotIn("a\n", text)
        self.assertIn("Use offset=4", text)

    async def test_read_missing_raises(self):
        with self.assertRaises(RuntimeError):
            await self.run_tool(create_read_tool(), {"path": "missing.txt"})

    async def test_edit_exact_replace(self):
        await self.run_tool(create_write_tool(), {"path": "e.txt", "content": "alpha\nbeta\ngamma\n"})
        result = await self.run_tool(
            create_edit_tool(),
            {"path": "e.txt", "edits": [{"oldText": "beta", "newText": "BETA"}]},
        )
        self.assertIn("Successfully replaced 1", result.content[0].text)
        text = (self.root / "e.txt").read_text()
        self.assertIn("BETA", text)
        self.assertNotIn("\nbeta", text)

    async def test_edit_non_unique_raises(self):
        await self.run_tool(create_write_tool(), {"path": "e.txt", "content": "dup\ndup\n"})
        with self.assertRaises(RuntimeError):
            await self.run_tool(
                create_edit_tool(), {"path": "e.txt", "edits": [{"oldText": "dup", "newText": "x"}]}
            )

    async def test_edit_fuzzy_fallback(self):
        await self.run_tool(create_write_tool(), {"path": "e.txt", "content": "original line\n"})
        result = await self.run_tool(
            create_edit_tool(),
            {"path": "e.txt", "edits": [{"oldText": "origina line", "newText": "fixed"}]},
        )
        self.assertIn("Successfully replaced 1", result.content[0].text)
        self.assertIn("fixed", (self.root / "e.txt").read_text())

    async def test_edit_preserves_crlf(self):
        await self.run_tool(
            create_write_tool(), {"path": "w.txt", "content": "one\r\ntwo\r\nthree\r\n"}
        )
        await self.run_tool(
            create_edit_tool(), {"path": "w.txt", "edits": [{"oldText": "two", "newText": "TWO"}]}
        )
        content = (self.root / "w.txt").read_bytes()
        self.assertIn(b"\r\nTWO", content)
        self.assertIn(b"\r\n", content)

    async def test_bash_success(self):
        result = await self.run_tool(create_bash_tool(), {"command": "echo done"})
        self.assertIn("done", result.content[0].text)

    async def test_bash_nonzero_exit_raises(self):
        with self.assertRaises(RuntimeError) as cm:
            await self.run_tool(create_bash_tool(), {"command": "exit 3"})
        self.assertIn("code 3", str(cm.exception))

    async def test_bash_timeout_raises_and_kills(self):
        with self.assertRaises(RuntimeError) as cm:
            await self.run_tool(create_bash_tool(), {"command": "sleep 30", "timeout": 1})
        self.assertIn("aborted", str(cm.exception))

    async def test_bash_truncation_persists_full_output(self):
        command = "python3 -c 'print(\"\\n\".join(str(i) for i in range(5000)))'"
        result = await self.run_tool(create_bash_tool(), {"command": command})
        text = result.content[0].text
        self.assertIn("Full output:", text)
        self.assertIn("full_output_path", result.details)
        self.assertTrue(Path(result.details["full_output_path"]).name.startswith("fruitfly-bash-"))
        full = Path(result.details["full_output_path"]).read_text()
        self.assertIn("4999", full)

    async def test_read_oversized_line_explains_partial_line(self):
        (self.root / 'long.txt').write_text('Ａ' * 40000 + '\nnext')
        result = await self.run_tool(create_read_tool(), {'path': 'long.txt'})
        body, hint = result.content[0].text.split('\n\n', 1)
        self.assertLessEqual(len(body.encode('utf-8')), 51200)
        self.assertIn('Line 1', hint)
        self.assertIn('omitted characters', hint)
        (self.root / 'long.txt').write_text('Ａ' * 40000)
        result = await self.run_tool(create_read_tool(), {'path': 'long.txt'})
        self.assertNotIn('offset=2', result.content[0].text)

    async def test_bash_cancellation_output_is_bounded_and_failed_save_is_explicit(self):
        async def execute(*args):
            return Result.success(ExecResult(stdout='x' * 80000, stderr='', exit_code=0, cancelled=True))
        with patch.object(self.env, 'exec', execute), patch.object(
            self.env, 'write_file', return_value=Result.failure('offline disk full')
        ):
            with self.assertRaises(RuntimeError) as failure:
                await self.run_tool(create_bash_tool(), {'command': 'unused'})
        text = str(failure.exception)
        self.assertLess(len(text.encode('utf-8')), 52000)
        self.assertIn('could not be saved', text)
        self.assertIn('Command aborted', text)
        self.assertNotIn('Full output:', text)


if __name__ == "__main__":
    unittest.main()
