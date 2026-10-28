"""Experiment composition cannot become a dependency of runtime or algorithms."""
import unittest
from tests.architecture.checks import ROOT, _project_imports, boundary_violations


class ExperimentBoundaryTests(unittest.TestCase):
    def test_runtime_layers_never_import_the_experiment_entry(self):
        for name in ('core', 'providers', 'interactive', 'lab', 'run'):
            for path in (ROOT / 'fruitfly_agent' / name).rglob('*.py'):
                self.assertFalse(any(t.startswith('fruitfly_agent.experiments') for t in _project_imports(path)), str(path))

    def test_new_composition_edge_does_not_allow_reverse_imports(self):
        self.assertEqual([], boundary_violations('from eval.api import run_evaluation\nfrom fruitfly_agent.run import RunApplicationFactory', 'fruitfly_agent.experiments.composition'))
        for layer in ('core', 'providers', 'interactive', 'lab', 'run'):
            self.assertTrue(boundary_violations('from fruitfly_agent.experiments import cli', 'fruitfly_agent.' + layer + '.example'))

    def test_common_workflow_contains_no_harness2_diagnostic_scopes(self):
        source = (ROOT / 'fruitfly_agent/improvement/workflow/controller.py').read_text()
        self.assertNotIn("'invariant'", source)
        self.assertNotIn("'domain'", source)
