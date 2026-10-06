"""Prove that forbidden dependencies are detected, not merely absent today."""
import unittest
from tests.architecture.checks import boundary_violations, imported_modules


class GuardDetectionTests(unittest.TestCase):
    def test_nested_and_type_checking_imports_cannot_cross_layers(self):
        for code in (
            'def factory():\n    import fruitfly_agent.lab.tools',
            'from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from eval import execution',
        ):
            with self.subTest(code=code):
                self.assertTrue(boundary_violations(code, 'fruitfly_agent.core.example'))

    def test_relative_imports_cannot_cross_layers(self):
        self.assertTrue(boundary_violations('from ..lab import tools', 'fruitfly_agent.core.example'))
        self.assertTrue(boundary_violations('from ..lab import tools', 'fruitfly_agent.core', True))

    def test_dynamic_imports_and_importlib_aliases_cannot_cross_layers(self):
        for code in (
            '__import__("eval.execution")',
            'import importlib\nimportlib.import_module("fruitfly_agent.lab.tools")',
            'import importlib as loader\nloader.import_module("eval")',
            'from importlib import import_module as load\nload("eval.execution")',
            'from importlib import import_module\nimport_module(name="eval.execution")',
        ):
            with self.subTest(code=code):
                self.assertTrue(boundary_violations(code, 'fruitfly_agent.core.example'))

    def test_literal_relative_dynamic_import_is_resolved(self):
        code = 'import importlib\nimportlib.import_module("..lab.tools", package="fruitfly_agent.core")'
        self.assertTrue(boundary_violations(code, 'fruitfly_agent.core.example'))

    def test_computed_dynamic_targets_require_explicit_static_identity(self):
        self.assertTrue(boundary_violations('import importlib\nimportlib.import_module(name)', 'fruitfly_agent.core.example'))

    def test_production_cannot_depend_on_test_support(self):
        for code in ('from tests.support import faux_provider', '__import__("tests.support")'):
            with self.subTest(code=code):
                self.assertTrue(boundary_violations(code, 'fruitfly_agent.run.example'))

    def test_core_cannot_import_provider_or_benchmark_sdks(self):
        for code in ('import openai', 'from anthropic import Anthropic', '__import__("harbor.job")'):
            with self.subTest(code=code):
                self.assertTrue(boundary_violations(code, 'fruitfly_agent.core.example'))
        self.assertEqual([], boundary_violations('import openai', 'fruitfly_agent.providers.example'))

    def test_legal_extensions_and_stdlib_imports_are_allowed(self):
        code = 'import asyncio\nfrom fruitfly_agent.core import AgentTool\nfrom . import models'
        self.assertEqual([], boundary_violations(code, 'fruitfly_agent.lab.example'))
        self.assertEqual([], boundary_violations('import importlib\nimportlib.import_module("readline")', 'fruitfly_agent.interactive.example'))

    def test_import_from_submodule_retains_parent_dependency(self):
        self.assertEqual(['fruitfly_agent.lab.tools'], imported_modules('from fruitfly_agent.lab import tools', 'fruitfly_agent.run.example'))
