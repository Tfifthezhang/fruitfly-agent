"""Packaged retained defaults and Skill content load without checkout fallback."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from fruitfly_eval.harbor.material import source_snapshot


class RetainedResourceTests(unittest.TestCase):
    def test_frozen_material_loads_skills_and_maintenance_defaults_in_isolated_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            frozen = root / 'source'
            source_snapshot(Path(__file__).resolve().parents[2], frozen)
            script = '''import sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
import fruitfly_agent
assert Path(fruitfly_agent.__file__).resolve().is_relative_to(root)
from fruitfly_agent.lab.catalog import builtin_catalog
from fruitfly_agent.lab.context_manager.augmentation.skills.library import builtin_entries
assert len(builtin_entries()) == 4
catalog = builtin_catalog()
assert catalog.get('file-memory').descriptor.normalize_parameters({})['extract_after_user_chars'] == 8000
assert catalog.get('file-memory').descriptor.normalize_parameters({})['extraction']
print('retained resources loaded from frozen material')
'''
            result = subprocess.run([sys.executable, '-I', '-c', script, str(frozen)], cwd=root,
                capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn('loaded from frozen material', result.stdout)

    def test_frozen_maintenance_journal_restores_responses_without_personal_storage(self):
        from fruitfly_agent.run.storage.artifacts import DataArtifactStore
        from fruitfly_agent.run.storage.retained_state import RetainedStateStore
        from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            personal = root / 'personal'
            store = RetainedStateStore(personal / 'memory', DataArtifactStore(personal / 'artifacts'),
                snapshot_directory='.fruitfly/retained/user')
            checkpoint = store.read()
            operation = store.begin('extract', 'frozen-call', request={'operation': 'extract'}, checkpoint=checkpoint)
            journal = store.read_journal(store.read()['operations'][operation])
            journal['calls'].append({'input': content_hash('input'), 'started': True,
                'response': store.artifacts.put_text('[]').artifact_id})
            store.record_journal(operation, journal)
            frozen = root / 'frozen'
            source_snapshot(Path(__file__).resolve().parents[2], frozen)
            for file in store.freeze().files:
                destination = frozen / file.path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(file.content)
            script = '''import sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
from fruitfly_agent.run.storage.artifacts import DataArtifactStore
from fruitfly_agent.run.storage.retained_state import RetainedStateStore
import fruitfly_agent.run.storage.retained_state as module
assert Path(module.__file__).resolve().is_relative_to(root)
store = RetainedStateStore(root / '.fruitfly/retained/user', DataArtifactStore(root / '.fruitfly/artifacts'))
state = store.read()
operation = next(iter(state['operations'].values()))
journal = store.read_journal(operation)
assert store.artifacts.read_text(journal['calls'][0]['response']) == '[]'
assert state['processed'] == 0
print('durable response recovered from frozen material')
'''
            result = subprocess.run([sys.executable, '-I', '-c', script, str(frozen)], cwd=root,
                capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn('durable response recovered', result.stdout)
