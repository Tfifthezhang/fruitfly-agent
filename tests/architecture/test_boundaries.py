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
            ROOT / "fruitfly_agent" / "interactive" / "contracts" / "configuration.py",
            ROOT / "fruitfly_agent" / "interactive" / "contracts" / "events.py",
            ROOT / "fruitfly_agent" / "interactive" / "contracts" / "models.py",
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
            for path in sorted(terminal.rglob("*.py"))
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
    def test_run_services_do_not_depend_on_composition_or_foreign_private_state(self):
        run = ROOT / "fruitfly_agent" / "run"
        forbidden = {
            "configuration": ("fruitfly_agent.run.application", "fruitfly_agent.run.runtime",
                              "fruitfly_agent.run.improvement", "fruitfly_agent.run.adapters"),
            "storage": ("fruitfly_agent.run.application", "fruitfly_agent.run.runtime",
                        "fruitfly_agent.run.improvement", "fruitfly_agent.run.adapters"),
            "runtime": ("fruitfly_agent.run.application", "fruitfly_agent.run.improvement",
                        "fruitfly_agent.run.adapters"),
            "improvement": ("fruitfly_agent.run.application", "fruitfly_agent.run.adapters"),
            "adapters": ("fruitfly_agent.run.application",),
        }
        violations = []
        for package, prefixes in forbidden.items():
            for path in (run / package).glob("*.py"):
                for target in _project_imports(path):
                    if target.startswith(prefixes):
                        violations.append(f"{path.relative_to(run)} imports {target}")
                for node in ast.walk(ast.parse(path.read_text())):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__init__":
                        arguments = (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
                        if any(argument.arg in {"factory", "controller"} for argument in arguments):
                            violations.append(f"{path.relative_to(run)} receives a composition owner")
                    if (isinstance(node, ast.Attribute) and node.attr.startswith("_")
                            and not (node.attr.startswith("__") and node.attr.endswith("__"))):
                        own = isinstance(node.value, ast.Name) and node.value.id in {"self", "cls"}
                        if not own:
                            violations.append(f"{path.relative_to(run)} accesses foreign private attribute {node.attr}")
        self.assertEqual([], violations)

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


class InteractiveExtensibilityTests(unittest.TestCase):
    def test_helpers_do_not_depend_on_application_or_foreign_private_state(self):
        interactive = ROOT / "fruitfly_agent" / "interactive"
        features = interactive / "terminal" / "features"
        paths = [interactive / "application" / "jobs.py", interactive / "session" / "materials.py",
                 features / "configuration" / "model_setup.py", features / "assembly.py",
                 *sorted(features.glob("*/command.py"))]
        violations = []
        for path in paths:
            for target in _project_imports(path):
                if target.startswith(("fruitfly_agent.interactive.application.application", "fruitfly_agent.run",
                                      "fruitfly_agent.interactive.terminal.frontend")):
                    violations.append(f"{path.name} imports {target}")
            for node in ast.walk(ast.parse(path.read_text())):
                if (isinstance(node, ast.Attribute) and node.attr.startswith("_")
                        and not (node.attr.startswith("__") and node.attr.endswith("__"))):
                    own = isinstance(node.value, ast.Name) and node.value.id in {"self", "cls"}
                    if not own:
                        violations.append(f"{path.name} accesses foreign private attribute {node.attr}")
        self.assertEqual([], violations)

    def test_input_loop_dispatches_commands_without_feature_branches(self):
        path = ROOT / "fruitfly_agent" / "interactive" / "terminal" / "frontend.py"
        tree = ast.parse(path.read_text())
        loop = next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "_run_loop")
        branches = [node.attr for node in ast.walk(loop) if isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name) and node.value.id == "command"]
        self.assertEqual([], branches, "Register a terminal handler instead of branching in the input loop")

    def test_services_do_not_bundle_unrelated_capabilities(self):
        from fruitfly_agent.interactive.contracts.optimization import OptimizationService
        from fruitfly_agent.interactive.contracts.candidates import CandidateService
        from fruitfly_agent.interactive.contracts.task_packs import TaskPackService
        self.assertFalse(hasattr(OptimizationService, "candidates"))
        self.assertFalse(hasattr(OptimizationService, "task_packs"))
        self.assertFalse(hasattr(CandidateService, "optimize"))
        self.assertFalse(hasattr(TaskPackService, "optimize"))


class InteractiveDirectoryTests(unittest.TestCase):
    def test_responsibility_dependencies_follow_directory_boundaries(self):
        interactive = ROOT / "fruitfly_agent" / "interactive"
        base = "fruitfly_agent.interactive."
        allowed = {
            "contracts": ("fruitfly_agent.core.", base + "contracts."),
            "interaction": ("fruitfly_agent.core.", base + "contracts.", base + "interaction."),
            "session": ("fruitfly_agent.core.", base + "contracts.", base + "session.", base + "interaction."),
            "application": ("fruitfly_agent.core.", base + "contracts.", base + "application.", base + "session.", base + "interaction."),
            "terminal/io": (base + "terminal.io.",),
            "terminal/rendering": (base + "contracts.", base + "terminal.io.", base + "terminal.rendering."),
        }
        violations = []
        for package, prefixes in allowed.items():
            for path in (interactive / package).rglob("*.py"):
                for target in _project_imports(path):
                    if not target.startswith(prefixes):
                        violations.append(f"{path.relative_to(interactive)} imports {target}")
        features = interactive / "terminal" / "features"
        for feature in ("configuration", "resume", "evaluation", "optimization"):
            prefixes = (base + "contracts.", base + "terminal.io.", base + "terminal.rendering.",
                        base + "terminal.bindings.", base + "terminal.commands.",
                        base + f"terminal.features.{feature}.")
            for path in (features / feature).rglob("*.py"):
                for target in _project_imports(path):
                    if not target.startswith(prefixes):
                        violations.append(f"{path.relative_to(interactive)} imports {target}")
        self.assertEqual([], violations, "Depend on public contracts or a lower responsibility layer")

    def test_interactive_root_and_terminal_root_keep_only_composition_entries(self):
        interactive = ROOT / "fruitfly_agent" / "interactive"
        self.assertEqual({"__init__.py"}, {path.name for path in interactive.glob("*.py")})
        self.assertEqual({"__init__.py", "frontend.py", "bindings.py", "commands.py", "notifications.py"},
                         {path.name for path in (interactive / "terminal").glob("*.py")})
        self.assertFalse((interactive / "terminal" / "actions").exists())

    def test_concrete_runtime_owner_satisfies_the_public_handle_protocol(self):
        from fruitfly_agent.interactive import RuntimeHandle
        from fruitfly_agent.interactive.contracts.runtime import RuntimeHandle as HandleContract
        from tests.support.application import offline_session
        from typing import get_type_hints
        handle = RuntimeHandle(offline_session(), {})
        for name in ("start", "health", "close", "session", "manifest", "optimization", "candidates",
                     "task_packs", "candidate_activation", "authorization", "activate_callback"):
            self.assertTrue(hasattr(handle, name), name)
        from fruitfly_agent.interactive.contracts.candidates import CandidateActivationService
        self.assertIs(HandleContract, get_type_hints(CandidateActivationService.prepare_candidate, localns={"RuntimeHandle": HandleContract})["return"])
