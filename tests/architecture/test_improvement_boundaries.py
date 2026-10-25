"""Editing, assessment, execution and RSI retain independent owners."""
import unittest
from tests.architecture.checks import ROOT, _project_imports


class ImprovementBoundaryTests(unittest.TestCase):
    def test_assessment_has_no_concrete_editor_or_host_imports(self):
        root = ROOT / 'fruitfly_agent/lab/improvement/assessment'
        forbidden = ('fruitfly_agent.lab.improvement.editor', 'fruitfly_agent.run', 'fruitfly_agent.interactive', 'eval')
        violations = [f'{p.name}: {target}' for p in root.rglob('*.py') for target in _project_imports(p)
            if target.startswith(forbidden)]
        self.assertEqual(violations, [])

    def test_editing_implementation_does_not_import_assessment_implementation(self):
        root = ROOT / 'fruitfly_agent/lab/improvement/editor'
        # The explicitly documented __init__ facade retains legacy imports.
        violations = [f'{p.name}: {target}' for p in root.glob('*.py') if p.name != '__init__.py'
            for target in _project_imports(p) if target.startswith('fruitfly_agent.lab.improvement.assessment')]
        self.assertEqual(violations, [])

    def test_improvement_does_not_import_rsi_or_benchmarks(self):
        root = ROOT / 'fruitfly_agent/lab/improvement'
        violations = [f'{p.name}: {target}' for p in root.rglob('*.py') for target in _project_imports(p)
            if target.startswith(('fruitfly_agent.lab.rsi', 'eval'))]
        self.assertEqual(violations, [])

    def test_batch_execution_receives_aggregation_instead_of_importing_a_scorer(self):
        path = ROOT / 'fruitfly_agent/lab/improvement/execution/batches.py'
        violations = [target for target in _project_imports(path)
            if target.startswith(('fruitfly_agent.lab.improvement.assessment',
                                  'fruitfly_agent.lab.improvement.editor', 'eval'))]
        self.assertEqual(violations, [])

    def test_shared_round_engine_does_not_select_task_or_backend_implementations(self):
        path = ROOT / 'fruitfly_agent/lab/improvement/workflow/engine.py'
        forbidden = ('fruitfly_agent.lab.improvement.task_sets',
                     'fruitfly_agent.lab.improvement.execution',
                     'fruitfly_agent.lab.improvement.assessment',
                     'fruitfly_agent.lab.improvement.editor',
                     'fruitfly_agent.run', 'fruitfly_agent.experiments', 'eval')
        self.assertEqual([target for target in _project_imports(path)
                          if target.startswith(forbidden)], [])
