"""Context policies retain method ownership and real Improvement admission."""
import unittest
from fruitfly_agent.lab.catalog import builtin_catalog
from tests.architecture.checks import ROOT, imported_modules


class ContextMethodBoundaries(unittest.TestCase):
    def test_reduction_definitions_declare_method_owned_implementations_and_editable_prompts(self):
        catalog = builtin_catalog()
        for identity, method, prompt in (('working-memory-reduction', 'working_memory', 'update_instructions'),):
            definition = catalog.get(identity)
            path = 'fruitfly_agent/lab/context_manager/reduction/methods/' + method + '/'
            self.assertEqual(path + 'algorithm.py', definition.implementation_path)
            self.assertIn(prompt, {p.name for p in definition.descriptor.parameters})
            self.assertIsNotNone(definition.configuration_edit)
            self.assertEqual({'editable_fields': ['parameters.instructions.update'], 'bounds': {}},
                definition.configuration_edit(['parameters.instructions.update'], {}))
        root = ROOT / 'fruitfly_agent/lab/context_manager/reduction'
        self.assertTrue((root / 'improvement.py').is_file())
        for obsolete in ('summarizing.py', 'config.py', 'estimate.py'):
            self.assertFalse((root / obsolete).exists())
        for path in (root / 'methods').rglob('*.py'):
            parts = path.relative_to(ROOT).with_suffix('').parts
            package = parts[-1] == '__init__'
            module = '.'.join(parts[:-1] if package else parts)
            for imported in imported_modules(path.read_text(), module, package):
                self.assertFalse(any('.methods.' + sibling in imported for sibling in ('working_memory', 'summarizing')
                    if sibling != path.parent.name), str(path))
