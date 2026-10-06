"""Production import and algorithm-host boundaries."""
import ast
import unittest
from tests.architecture.checks import ROOT, SOURCE_ROOTS, boundary_violations, _module_info, _project_imports


class LayeringTest(unittest.TestCase):
    def test_import_directions(self) -> None:
        violations = []
        for source_root in SOURCE_ROOTS:
            for path in sorted(source_root.rglob("*.py")):
                source, is_pkg = _module_info(path)
                violations.extend(boundary_violations(path.read_text(encoding="utf-8"), source, is_pkg))
        self.assertEqual([], violations,
                         'Module dependency boundary violation: use existing public contracts; do not widen dependency allowances to silence failures.')

    def test_interactive_contracts_are_core_independent(self) -> None:
        contract_files = (
            ROOT / "fruitfly_agent" / "interactive" / "configuration.py",
            ROOT / "fruitfly_agent" / "interactive" / "events.py",
            ROOT / "fruitfly_agent" / "interactive" / "models.py",
        )
        violations = [
            f"{path.name} imports {target}"
            for path in contract_files
            for target in _project_imports(path)
        ]
        self.assertEqual([], violations)

    def test_terminal_adapter_does_not_import_runtime_layers(self) -> None:
        terminal = ROOT / "fruitfly_agent" / "interactive" / "terminal"
        forbidden = (
            "fruitfly_agent.core",
            "fruitfly_agent.providers",
            "fruitfly_agent.lab",
            "eval",
        )
        violations = [
            f"{path.name} imports {target}"
            for path in sorted(terminal.glob("*.py"))
            for target in _project_imports(path)
            if target.startswith(forbidden)
        ]
        self.assertEqual([], violations)

    def test_interactive_does_not_encode_builtin_mechanism_ids(self) -> None:
        interactive = ROOT / "fruitfly_agent" / "interactive"
        identifiers = {
            "local-env",
            "read-tool",
            "bash-tool",
            "edit-tool",
            "write-tool",
            "skill-catalog",
            "information-context",
            "memory-files",
            "knowledge-files",
            "live-http",
            "lessons",
        }
        violations = []
        for path in sorted(interactive.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            literals = {
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            }
            violations.extend(
                f"{path.relative_to(interactive)} contains {identifier}"
                for identifier in sorted(identifiers & literals)
            )
        self.assertEqual([], violations)

class RunAlgorithmBoundaryTests(unittest.TestCase):
    def test_run_only_imports_public_lab_host_contracts(self):
        allowed = {"fruitfly_agent.lab.catalog", "fruitfly_agent.lab.catalog.models",
                   "fruitfly_agent.lab.base_prompt", "fruitfly_agent.lab.optimization.text_optimizer", "fruitfly_agent.lab.optimization.task_packs",
                   "fruitfly_agent.lab.algorithms.targets", "fruitfly_agent.lab.algorithms.evolution"}
        violations = []
        for path in (ROOT / "fruitfly_agent" / "run").rglob("*.py"):
            for target in _project_imports(path):
                module = target.rsplit(".", 1)[0] if target not in allowed else target
                if target.startswith("fruitfly_agent.lab") and target not in allowed and module not in allowed:
                    violations.append(f"{path.name}: {target}")
        self.assertEqual([], violations)

    def test_frontend_and_host_have_no_concrete_algorithm_branches(self):
        forbidden = {"gepa", "GEPA", "opro", "OPRO", "mce", "MCE", "Pareto", "max_metric_calls", "max_reflection_calls", "reflection_max_tokens", "information-context", "skill-catalog.guidance", "local-env"}
        violations = []
        for directory in (ROOT / "fruitfly_agent" / "run", ROOT / "fruitfly_agent" / "interactive"):
            for path in directory.rglob("*.py"):
                tree = ast.parse(path.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        found = {word for word in forbidden if word in node.value}
                        if found:
                            violations.append(f"{path.name}: {sorted(found)}")
        self.assertEqual([], violations)
