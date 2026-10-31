"""Editing, assessment, execution and RSI retain independent owners."""
import unittest
from tests.architecture.checks import ROOT, _project_imports


class ImprovementBoundaryTests(unittest.TestCase):
    def test_concrete_stage_implementations_retain_their_lab_owners(self):
        from fruitfly_agent.lab.improvement.editor import AgentEditor
        from fruitfly_agent.lab.improvement.assessment.selection import AgentSelector
        from fruitfly_agent.lab.improvement.experience.reflection import AgentReflector
        from fruitfly_agent.lab.improvement.termination import BoundedStopPolicy
        from fruitfly_agent.lab.improvement.assessment.aggregation import WeightedSum
        for implementation, owner in (
            (AgentEditor, 'editor'), (AgentSelector, 'assessment'),
            (AgentReflector, 'experience'), (BoundedStopPolicy, 'termination'),
            (WeightedSum, 'assessment'),
        ):
            with self.subTest(implementation=implementation.__name__):
                self.assertTrue(implementation.__module__.startswith(
                    'fruitfly_agent.lab.improvement.' + owner + '.'))

    def test_assessment_has_no_concrete_editor_or_host_imports(self):
        root = ROOT / 'fruitfly_agent/lab/improvement/assessment'
        forbidden = ('fruitfly_agent.lab.improvement.editor', 'fruitfly_agent.run', 'fruitfly_agent.interactive', 'fruitfly_eval')
        violations = [f'{p.name}: {target}' for p in root.rglob('*.py') for target in _project_imports(p)
            if target.startswith(forbidden)]
        self.assertEqual(violations, [])

    def test_editing_implementation_does_not_import_assessment_implementation(self):
        root = ROOT / 'fruitfly_agent/lab/improvement/editor'
        violations = [f'{p.name}: {target}' for p in root.glob('*.py')
            for target in _project_imports(p) if target.startswith('fruitfly_agent.lab.improvement.assessment')]
        self.assertEqual(violations, [])

    def test_improvement_does_not_import_rsi_or_benchmarks(self):
        root = ROOT / 'fruitfly_agent/lab/improvement'
        violations = [f'{p.name}: {target}' for p in root.rglob('*.py') for target in _project_imports(p)
            if target.startswith(('fruitfly_agent.rsi', 'fruitfly_eval'))]
        self.assertEqual(violations, [])

    def test_batch_execution_receives_aggregation_instead_of_importing_a_scorer(self):
        path = ROOT / 'fruitfly_agent/improvement/execution/batches.py'
        violations = [target for target in _project_imports(path)
            if target.startswith(('fruitfly_agent.lab.improvement.assessment',
                                  'fruitfly_agent.lab.improvement.editor', 'fruitfly_eval'))]
        self.assertEqual(violations, [])

    def test_shared_round_engine_does_not_select_task_or_backend_implementations(self):
        path = ROOT / 'fruitfly_agent/improvement/workflow/engine.py'
        forbidden = ('fruitfly_agent.lab.improvement.task_sets',
                     'fruitfly_agent.lab.improvement.execution',
                     'fruitfly_agent.lab.improvement.assessment',
                     'fruitfly_agent.lab.improvement.editor',
                     'fruitfly_agent.run', 'fruitfly_agent.experiments', 'fruitfly_eval')
        self.assertEqual([target for target in _project_imports(path)
                          if target.startswith(forbidden)], [])

    def test_runtime_kernel_depends_only_on_itself_core_and_standard_library(self):
        import sys
        from tests.architecture.checks import imported_modules, _module_info
        violations = []
        for path in (ROOT / 'fruitfly_agent/improvement').rglob('*.py'):
            module, package = _module_info(path)
            for target in imported_modules(path.read_text(), module, package):
                if target.startswith(('fruitfly_agent.improvement', 'fruitfly_agent.core')):
                    continue
                if target.split('.')[0] not in sys.stdlib_module_names:
                    violations.append(f'{path.relative_to(ROOT)}: {target}')
        self.assertEqual(violations, [])

    def test_kernel_can_import_when_lab_run_eval_and_providers_are_unavailable(self):
        import subprocess
        import sys
        source = '''
import importlib.abc
import sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('fruitfly_agent.lab', 'fruitfly_agent.run',
                                'fruitfly_agent.providers', 'fruitfly_agent.interactive', 'fruitfly_eval')):
            raise ImportError('forbidden dependency: ' + fullname)
sys.meta_path.insert(0, Block())
from fruitfly_agent.improvement.api import ImprovementWorkflow, WorkflowServices
'''
        result = subprocess.run([sys.executable, '-B', '-c', source], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
