"""The interactive harness runs when the optional eval package is unavailable."""
import subprocess
import sys
import unittest
from tests.architecture.checks import ROOT


class OptionalEvalTests(unittest.TestCase):
    def test_main_cli_and_offline_application_work_without_eval(self):
        script = r'''
import importlib.abc
import sys
class NoEval(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'eval' or fullname.startswith('eval.'):
            raise ModuleNotFoundError('eval intentionally unavailable')
sys.meta_path.insert(0, NoEval())
import asyncio
import contextlib
import io
import tempfile
from pathlib import Path
from unittest.mock import Mock
from fruitfly_agent.run import main
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.interactive import AgentApplication
from tests.support.faux_provider import FauxProvider
from tests.support.materials import _write_models
with contextlib.redirect_stdout(io.StringIO()) as output:
    sys.argv = ['fruitfly-agent', '--help']
    try:
        main()
    except SystemExit as exit:
        assert exit.code == 0
assert 'usage:' in output.getvalue()
async def check():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_models(root)
        provider = FauxProvider()
        provider.respond_text('ready')
        registry = Mock()
        registry.create.return_value = provider
        app = AgentApplication(RunApplicationFactory(cwd=root, environment={}, provider_registry=registry))
        await app.start()
        try:
            result = await app.submit('hello')
            assert not result.is_error
            assert len(provider.calls) == 1
        finally:
            await app.close()
asyncio.run(check())
assert not any(name == 'eval' or name.startswith('eval.') for name in sys.modules)
print('optional-eval-independent')
'''
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn('optional-eval-independent', result.stdout)
