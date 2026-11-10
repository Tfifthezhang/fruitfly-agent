"""Frozen runtime resources support actual child construction without checkout imports."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from fruitfly_eval.harbor.material import source_snapshot

class FrozenSubagentTests(unittest.TestCase):
    def test_frozen_material_runs_a_child_with_its_declared_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            frozen = root / 'source'
            source_snapshot(Path(__file__).resolve().parents[2], frozen)
            script = r"""
import sys, asyncio
from pathlib import Path
source = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(source))
from fruitfly_agent.lab.catalog import builtin_catalog, MechanismSelection
from fruitfly_agent.run.runtime.assembly import build_runtime
from fruitfly_agent.run.runtime import child_runtime
from fruitfly_agent.runtime_spec import HarnessProfile
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.interactive.application.runtime import RuntimeHandle
assert Path(child_runtime.__file__).resolve().is_relative_to(source)
class Provider:
    def __call__(self, view, *, signal=None):
        assert not any(t.name.startswith('subagent_') for t in view.tools)
        async def events():
            yield StreamDone(AssistantMessage([TextBlock('frozen child result')], 'stop'))
        return AssistantMessageEventStream(events())
class Registry:
    def create(self, spec, environment): return Provider()
async def run():
    workspace = Path(sys.argv[2])
    import yaml
    (workspace / 'models.yaml').write_text(yaml.safe_dump({'models': {'offline': {
        'sdk': 'anthropic', 'protocol': 'messages', 'model': 'offline',
        'api_key_env': 'OFFLINE_KEY', 'context_window': 16000, 'max_output_tokens': 4096}}}))
    with Session(workspace / 'root.jsonl') as session:
        runtime = build_runtime(HarnessProfile('frozen', model_profile='offline',
            mechanisms=(MechanismSelection('subagent'),)), config_path=workspace / 'config.yaml',
            catalog=builtin_catalog(), environment={}, session=session, cwd=workspace,
            provider_registry=Registry())
        owner = RuntimeHandle(None, {}, components=runtime.components)
        try:
            service = runtime.components['subagent-monitor']
            service.begin()
            row = service.spawn('Inspect frozen defaults')
            result = await service.wait([(row['agent_id'], row['run_id'])], timeout_seconds=2)
            assert result['executions'][0]['state'] == 'completed', result
            assert service.store.read_result(result['executions'][0])['output'] == 'frozen child result'
            await service.end()
        finally:
            await owner.close()
asyncio.run(run())
print('frozen subagent executed')
"""
            result = subprocess.run([sys.executable, '-I', '-c', script, str(frozen), str(root)],
                cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn('frozen subagent executed', result.stdout)
