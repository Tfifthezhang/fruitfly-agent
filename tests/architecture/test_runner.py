"""Public developer command never omits guards or selects paid smoke."""
import io
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import Mock, patch
from tests.runner import select_suites, cases, main


class DeveloperRunnerTests(unittest.TestCase):
    def test_help_describes_offline_selection_and_guards_in_english(self):
        with redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as result:
            main(['--help'])
        self.assertEqual(0, result.exception.code)
        help_text = ' '.join(output.getvalue().split())
        self.assertIn('Offline development checks', help_text)
        self.assertIn('guard checks are always included', help_text)
        self.assertIn('without executing test methods', help_text)

    def test_area_selection_includes_guards_and_only_requested_behavior(self):
        guards, behavior = select_suites(('providers',))
        self.assertEqual({'architecture', 'contracts'}, {c.__class__.__module__.split('.')[1] for c in cases(guards)})
        self.assertEqual({'providers'}, {c.__class__.__module__.split('.')[1] for c in cases(behavior)})

    def test_overlapping_module_and_area_are_deduplicated(self):
        guards, behavior = select_suites(('providers', 'providers'), ('tests.providers.test_providers',))
        ids = [c.id() for c in (*cases(guards), *cases(behavior))]
        self.assertEqual(len(ids), len(set(ids)))

    def test_default_selection_matches_standard_discovery(self):
        guards, behavior = select_suites()
        standard = unittest.TestLoader().discover('tests', top_level_dir='.')
        self.assertEqual({c.id() for c in cases(standard)}, {c.id() for c in (*cases(guards), *cases(behavior))})

    def test_paid_smoke_and_unknown_areas_are_rejected(self):
        for areas, modules in ((('integration',), ()), ((), ('tests.integration.provider_smoke',)), ((), ('os',))):
            with self.subTest(areas=areas, modules=modules), self.assertRaises(ValueError):
                select_suites(areas, modules)

    def test_guard_import_failure_stays_in_guard_phase(self):
        failed = unittest.TestLoader().loadTestsFromName('tests.contracts.test_missing_guard')
        with patch('tests.runner.unittest.TestLoader') as loader:
            loader.return_value.discover.side_effect = [unittest.TestSuite(), failed, unittest.TestSuite()]
            guards, behavior = select_suites(('providers',))
        self.assertEqual(1, guards.countTestCases())
        self.assertEqual(0, behavior.countTestCases())

    def test_guard_failure_stops_before_behavior(self):
        guards, behavior = unittest.TestSuite(), unittest.TestSuite([unittest.FunctionTestCase(lambda: None)])
        result = Mock()
        result.wasSuccessful.return_value = False
        with patch('tests.runner.select_suites', return_value=(guards, behavior)), patch('tests.runner.unittest.TextTestRunner') as runner, redirect_stderr(io.StringIO()):
            runner.return_value.run.return_value = result
            self.assertEqual(1, main(['--area', 'providers']))
            runner.return_value.run.assert_called_once_with(guards)

    def test_list_does_not_execute_tests(self):
        with patch('tests.runner.unittest.TextTestRunner') as runner, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, main(['--module', 'tests.providers.test_providers', '--list']))
            runner.assert_not_called()
        self.assertIn('tests.contracts.', output.getvalue())
        self.assertIn('tests.providers.', output.getvalue())
