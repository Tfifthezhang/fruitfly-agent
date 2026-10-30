"""Frozen source and wheel resources remain executable and content-bound."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from eval.harbor.host import HostConfig
from eval.harbor.material import check_material, prepare_material, source_snapshot
from eval.installation import SOURCE_FILES, installation_identity, validate_installation
from tests.architecture.checks import ROOT
from tests.support.harbor import prepared_harbor


class MaterialResourceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()

    def source(self):
        root = self.root / 'package'
        root.mkdir()
        for name in SOURCE_FILES:
            (root / name).write_text('Fixture build input')
        for name in ('fruitfly_agent', 'eval'):
            (root / name).mkdir()
            (root / name / '__init__.py').write_text('')
        (root / 'fruitfly_agent/assets').mkdir()
        (root / 'fruitfly_agent/assets/settings.txt').write_text('initial')
        (root / 'pyproject.toml').write_text(
            '[project]\nname="fruitfly-agent"\nversion="0.1"\n'
            '[tool.setuptools.package-data]\nfruitfly_agent=["assets/settings.txt", "assets/*.json"]\n')
        return root

    def test_declared_resources_are_copied_hashed_and_missing_named_resources_reject(self):
        source = self.source()
        (source / 'fruitfly_agent/assets/extra.json').write_text('{"enabled":true}')
        resource = source / 'fruitfly_agent/assets/settings.txt'
        original = installation_identity(source)
        resource.write_text('changed')
        self.assertNotEqual(original['sha256'], installation_identity(source)['sha256'])
        target = self.root / 'snapshot'
        identity = source_snapshot(source, target)
        self.assertEqual('changed', (target / 'fruitfly_agent/assets/settings.txt').read_text())
        self.assertIn('fruitfly_agent/assets/settings.txt', dict(identity['files']))
        self.assertEqual('{"enabled":true}', (target / 'fruitfly_agent/assets/extra.json').read_text())
        resource.unlink()
        with self.assertRaisesRegex(ValueError, 'resource'):
            validate_installation(source)

    def test_source_and_wheel_snapshots_import_providers_and_load_templates_in_isolation(self):
        wheel = self.root / 'fruitfly_agent-0.1-py3-none-any.whl'
        with zipfile.ZipFile(wheel, 'w') as archive:
            for directory in ('fruitfly_agent', 'eval'):
                for path in (ROOT / directory).rglob('*'):
                    if path.is_file() and path.suffix in {'.py', '.yaml'} and '__pycache__' not in path.parts:
                        archive.write(path, path.relative_to(ROOT).as_posix())
            archive.writestr('fruitfly_agent-0.1.dist-info/METADATA', 'Name: fruitfly-agent\nVersion: 0.1\n')
        for name, package in (('source', ROOT), ('wheel', wheel)):
            with self.subTest(material=name):
                target = self.root / name
                source_snapshot(package, target)
                code = '''
import sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root))
import fruitfly_agent.providers as providers
from fruitfly_agent.providers.services import builtin_services
from fruitfly_agent.experiments.scaffolding import workspace_templates
assert Path(providers.__file__).is_relative_to(root)
assert {item.id for item in builtin_services()} >= {'openai', 'anthropic', 'deepseek', 'qwen'}
assert 'default-config.yaml' in workspace_templates()
from fruitfly_agent.run import main
sys.argv = ['fruitfly-agent', '--help']
main()
'''
                result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(target)],
                    cwd=self.root, capture_output=True, text=True, timeout=20)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn('usage:', result.stdout)

    def test_resource_changes_create_fresh_preparation_and_old_formats_require_prepare(self):
        source = self.source()
        host, _ = prepared_harbor(self.root)
        (self.root / 'runtime').mkdir()
        (self.root / 'runtime/python').write_text('offline runtime identity fixture')
        first = prepare_material(host, source)
        resource = source / 'fruitfly_agent/assets/settings.txt'
        resource.write_text('new content')
        second = prepare_material(host, source)
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual('initial', (Path(first['source']) / resource.relative_to(source)).read_text())
        self.assertEqual('new content', (Path(second['source']) / resource.relative_to(source)).read_text())
        check_material(host, first)
        old = {**first, 'installation': {**first['installation'], 'schema_version': 1}}
        with self.assertRaisesRegex(ValueError, 'format changed; run eval prepare'):
            check_material(host, old)

    def test_source_excludes_undeclared_local_state_and_rejects_resource_symlinks(self):
        source = self.source()
        (source / '.env').write_text('OFFLINE_PLACEHOLDER=private')
        (source / 'fruitfly_agent/.env').write_text('OFFLINE_PLACEHOLDER=private')
        (source / 'fruitfly_agent/unregistered.yaml').write_text('private: fixture')
        target = self.root / 'snapshot'
        source_snapshot(source, target)
        for name in ('.env', 'fruitfly_agent/.env', 'fruitfly_agent/unregistered.yaml'):
            self.assertFalse((target / name).exists())
        resource = source / 'fruitfly_agent/assets/settings.txt'
        resource.unlink()
        resource.symlink_to(source / '.env')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            validate_installation(source)

    def test_wheel_record_missing_resources_and_unsafe_files_reject_before_freezing(self):
        wheel = self.root / 'broken.whl'
        for name in ('fruitfly_agent/providers/services.yaml', 'fruitfly_agent/../escape.py', 'fruitfly_agent/.env'):
            with self.subTest(member=name):
                with zipfile.ZipFile(wheel, 'w') as archive:
                    archive.writestr('fruitfly_agent/__init__.py', '')
                    archive.writestr('eval/__init__.py', '')
                    archive.writestr('fruitfly_agent-0.1.dist-info/METADATA', 'Name: fruitfly-agent\nVersion: 0.1\n')
                    if name.endswith('services.yaml'):
                        archive.writestr('fruitfly_agent-0.1.dist-info/RECORD', name + ',,\n')
                    else:
                        archive.writestr(name, 'invalid fixture material')
                with self.assertRaises(ValueError):
                    source_snapshot(wheel, self.root / 'rejected')
                self.assertFalse((self.root / 'rejected').exists())

    def test_repeated_host_yaml_keys_cannot_discard_task_patches_or_nested_settings(self):
        path = self.root / 'host.yaml'
        prefix = ('agent:\n  python: /opt/runtime/bin/python\n  mounts:\n'
                  '    - source: ./runtime\n      target: /opt/runtime\n')
        for suffix in ('task_patches: [{task: sample, path: tests/test.sh, old: a, new: b}]\ntask_patches: []\n',
                       'dependencies:\n  offline: true\n  offline: false\n'):
            with self.subTest(yaml=suffix):
                path.write_text(prefix + suffix)
                with self.assertRaisesRegex(ValueError, 'distinct|duplicate'):
                    HostConfig.read(self.root, path)
