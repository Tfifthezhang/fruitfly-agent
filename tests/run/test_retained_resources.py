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
assert catalog.get('memory-maintenance').descriptor.normalize_parameters({})['extract_after_user_chars'] == 8000
assert catalog.get('memory-extractor').descriptor.normalize_parameters({})['prompt']
print('retained resources loaded from frozen material')
'''
            result = subprocess.run([sys.executable, '-I', '-c', script, str(frozen)], cwd=root,
                capture_output=True, text=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn('loaded from frozen material', result.stdout)
