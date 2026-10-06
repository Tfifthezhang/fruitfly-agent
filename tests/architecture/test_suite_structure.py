"""Keep tests discoverable, fixtures independent, and paid smoke explicit."""
import ast
import unittest
from tests.architecture.checks import ROOT, imported_modules


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


class SuiteStructureTests(unittest.TestCase):
    def test_default_discovery_has_unique_ids_and_no_paid_smoke(self):
        suite = unittest.TestLoader().discover(str(ROOT / 'tests'), top_level_dir=str(ROOT))
        ids = [case.id() for case in cases(suite)]
        self.assertEqual(len(ids), len(set(ids)), 'TestCase imports can duplicate discovery')
        self.assertFalse(any('.integration.' in identity or '.support.' in identity for identity in ids))
        self.assertFalse(any('_FailedTest' in identity for identity in ids))
        discovered = {identity.rsplit('.', 2)[0] for identity in ids}
        expected = {'.'.join(p.relative_to(ROOT).with_suffix('').parts)
                    for p in (ROOT / 'tests').rglob('test_*.py')}
        self.assertEqual(expected, discovered, 'Every test file must contribute discoverable cases')

    def test_test_modules_do_not_import_other_test_modules(self):
        violations = []
        for path in (ROOT / 'tests').rglob('*.py'):
            source = '.'.join(path.relative_to(ROOT).with_suffix('').parts)
            for target in imported_modules(path.read_text(), source, path.name == '__init__.py'):
                if target.startswith('tests.') and any(part.startswith('test_') for part in target.split('.')):
                    violations.append(f'{source}: {target}')
        self.assertEqual([], violations, 'Extract shared fixtures into tests.support')

    def test_support_modules_do_not_define_cases_or_discovery_hooks(self):
        for path in (ROOT / 'tests/support').glob('*.py'):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                with self.subTest(file=path.name):
                    if isinstance(node, ast.ClassDef):
                        self.assertFalse(any('TestCase' in ast.unparse(base) for base in node.bases))
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.assertFalse(node.name.startswith('test_') or node.name == 'load_tests')

    def test_online_smoke_requires_explicit_module_execution(self):
        self.assertTrue((ROOT / 'tests/integration/provider_smoke.py').is_file())
        self.assertEqual([], list((ROOT / 'tests/integration').glob('test_*.py')))
