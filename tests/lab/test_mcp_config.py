"""MCP configuration is offline, explicit and independent of SDK imports."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml
from fruitfly_agent.lab.mcp.config import load_config
from tests.support.mcp import write_mcp_config


class McpConfigTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_relative_directory_and_secret_references_are_offline(self):
        path = write_mcp_config(self.root, cwd='.', secret_env={'TOKEN': 'FIXTURE_TOKEN'}, env={'MODE': 'offline'})
        config = load_config(path, self.root)[0]
        self.assertEqual(str(self.root.resolve()), config.cwd)
        self.assertEqual({'TOKEN': 'FIXTURE_TOKEN'}, config.secret_env)
        self.assertEqual({'MODE': 'offline'}, config.env)

    def test_invalid_fields_and_budgets_are_rejected(self):
        for changes in ({'tools': []}, {'tools': ['echo', 'echo']}, {'transport': 'http'},
                {'command': ''}, {'args': 'shell string'}, {'call_timeout': False},
                {'close_timeout': float('inf')}, {'max_parallel': 1.5}, {'unknown': True},
                {'env': {'TOKEN': 'value'}, 'secret_env': {'TOKEN': 'KEY'}},
                {'secret_env': {'TOKEN': 'literal with spaces'}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                load_config(write_mcp_config(self.root, **changes), self.root)

    def test_disabled_server_has_no_preparation(self):
        config = load_config(write_mcp_config(self.root, enabled=False), self.root)
        self.assertEqual((), config)

    def test_duplicate_yaml_fields_are_rejected(self):
        path = write_mcp_config(self.root)
        path.write_text('servers:\n  duplicate: {}\n  duplicate: {}\n')
        with self.assertRaisesRegex(ValueError, 'invalid MCP YAML'):
            load_config(path, self.root)

    def test_default_catalog_does_not_import_optional_dependencies(self):
        result = subprocess.run([sys.executable, '-c',
            "import sys; from fruitfly_agent.lab.catalog import builtin_catalog; c=builtin_catalog(); "
            "assert 'mcp-tools' not in {s.mechanism_id for s in c.default_selections()}; "
            "assert 'mcp' not in sys.modules; assert 'jsonschema' not in sys.modules"], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
