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
            mechanisms=(MechanismSelection('subagent', parameters={'inheritance_mode': 'explicit', 'inherited_components': []}),)), config_path=workspace / 'config.yaml',
            catalog=builtin_catalog(), environment={}, session=session, cwd=workspace,
            provider_registry=Registry())
        owner = RuntimeHandle(None, {}, components=runtime.components)
        try:
            service = runtime.components['subagent-monitor']
            assert service.protocol.max_task_characters == 16000
            assert service.results.output_page_characters == 4000
            service.begin()
            row = service.spawn('Inspect frozen defaults')
            result = await service.wait([(row['agent_id'], row['run_id'])], timeout_seconds=2)
            assert result['executions'][0]['state'] == 'completed', result
            assert service.store.read_result(result['executions'][0])['output'] == 'frozen child result'
            await service.end()
        finally:
            await owner.close()
async def research():
    import json, yaml
    from fruitfly_agent.core.config import AgentLoopConfig
    from fruitfly_agent.core.data_model import ToolCallBlock
    from fruitfly_agent.improvement.contracts.components import ComponentDocument, HarnessSnapshot
    from fruitfly_agent.lab.improvement.evidence import EvidenceWorkspace
    from fruitfly_agent.lab.improvement.evidence.session import EvidenceSession
    from fruitfly_agent.run.improvement.roles import ResearchRoles
    from fruitfly_agent.run.improvement import research_runtime
    from fruitfly_agent.run.storage.artifacts import DataArtifactStore
    assert Path(research_runtime.__file__).resolve().is_relative_to(source)
    workspace = Path(sys.argv[2])
    (workspace / 'research-config.yaml').write_text(yaml.safe_dump({
        'default_profile': 'offline', 'profiles': {'offline': {
            'models': {'catalog': 'models.yaml', 'roles': {'executor': 'offline'}},
            'H': {'subagent': {'default': True}}, 'S': {}, 'I': {}}}}))
    class Scripted:
        count = 0
        child = False
        def __call__(self, view, *, signal=None):
            self.count += 1
            if self.child:
                assert {t.name for t in view.tools} == {'catalog', 'search', 'read', 'submit_findings'}
                if self.count == 1:
                    message = AssistantMessage([ToolCallBlock('read', 'read', {'path': 'evidence.txt'})], 'toolUse')
                else:
                    page = json.loads(view.messages[-1].text)
                    message = AssistantMessage([ToolCallBlock('findings', 'submit_findings', {
                        'summary': 'Frozen evidence was read.', 'unknowns': [],
                        'sources': [{'path': 'evidence.txt', 'citation_id': page['citation_id']}]})], 'toolUse')
            elif self.count == 1:
                message = AssistantMessage([ToolCallBlock('spawn', 'subagent_spawn', {
                    'task': 'Inspect', 'worker': 'evidence-reader', 'materials': ['evidence.txt']})], 'toolUse')
            else:
                message = AssistantMessage([TextBlock('integrated')], 'stop')
            async def events(): yield StreamDone(message)
            return AssistantMessageEventStream(events())
    class ChildRegistry:
        def create(self, spec, environment):
            provider = Scripted(); provider.child = True; return provider
    class Services:
        signal = asyncio.Event()
        def check(self): pass
        def record(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
    roles = ResearchRoles(workspace, workspace / 'research-config.yaml', registry=ChildRegistry(), environment={})
    try:
        artifacts = DataArtifactStore(workspace / 'research-artifacts')
        from fruitfly_agent.run.storage.organization_parts import OrganizationPartStore
        parts = OrganizationPartStore(workspace / 'organization-parts', artifacts)
        settings = {'delegation': {'enabled': True}, 'retention': {'enabled': True}}
        factory = roles.runtime_factory('editor', workspace / 'roles', artifacts, settings, parts=parts)
        baseline = HarnessSnapshot((ComponentDocument('prompt', 'instructions', 'H', 'fixture', ()),))
        evidence = EvidenceWorkspace(baseline=baseline, files={'evidence.txt': b'frozen evidence'}, writable_ids=())
        result = await EvidenceSession(AgentLoopConfig(Scripted()), artifacts,
            settings=settings, runtime_factory=factory).session('Inspect', evidence, Services())
        assert result == 'integrated'
        assert evidence.eligible_paths('evidence.txt')
        assert not evidence.provided_ids
        assert len(parts.entries()) == 1
        part = parts.read(parts.entries()[0])
        assert part.findings['summary'] == 'Frozen evidence was read.'
        assert part.conditions['implementation_id'] == parts.implementation_id
    finally:
        await roles.aclose()
asyncio.run(run())
asyncio.run(research())
print('frozen subagent executed')
"""
            result = subprocess.run([sys.executable, '-I', '-c', script, str(frozen), str(root)],
                cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn('frozen subagent executed', result.stdout)
