"""Public exports and source responsibility invariants."""
import unittest
from tests.architecture.checks import ROOT
from tests.contracts.api_baseline import CORE_PUBLIC_API, DATA_MODEL_PUBLIC_API, ENV_CONTRACT_PUBLIC_API, LAB_ENV_PUBLIC_API, MODULE_EXPORTS

class PublicApiTest(unittest.TestCase):
    def test_legacy_core_paths_stay_removed_and_extensions_documented(self):
        for relative in (
            'core/llm/__init__.py', 'core/llm/stream.py', 'core/types.py',
            'core/context.py', 'core/protocols.py', 'core/hooks.py', 'core/wiring.py',
        ):
            with self.subTest(path=relative):
                self.assertFalse((ROOT / 'fruitfly_agent' / relative).exists(),
                                 f'Legacy path {relative} must not return as a compatibility shadow package; use the current public contracts.')
        self.assertTrue((ROOT / 'fruitfly_agent/core/extensions/README.md').is_file())



    def test_core_env_contains_contracts_and_lab_contains_implementations(self) -> None:
        core_env = ROOT / "fruitfly_agent" / "core" / "env"
        self.assertFalse((core_env / "base.py").exists())
        self.assertTrue((core_env / "types.py").is_file())
        self.assertTrue((core_env / "protocols.py").is_file())
        self.assertTrue((core_env / "README.md").is_file())
        self.assertFalse((core_env / "local_filesystem.py").exists())
        self.assertFalse((core_env / "local_shell.py").exists())
        self.assertFalse((core_env / "local.py").exists())

        lab_env = ROOT / "fruitfly_agent" / "lab" / "environment"
        self.assertTrue((lab_env / "local.py").is_file())
        self.assertTrue((lab_env / "README.md").is_file())
        self.assertFalse((lab_env / "local_filesystem.py").exists())
        self.assertFalse((lab_env / "local_shell.py").exists())

    def test_concrete_research_mechanisms_live_outside_core(self) -> None:
        core = ROOT / "fruitfly_agent" / "core"
        self.assertFalse((core / "skills.py").exists())
        self.assertFalse((core / "compaction").exists())
        self.assertFalse((core / "tools").exists())
        self.assertTrue((core / "tool_runtime" / "__init__.py").is_file())
        self.assertTrue((core / "tool_runtime" / "schema.py").is_file())
        self.assertTrue((core / "tool_runtime" / "README.md").is_file())

    def test_search_tool_is_removed_from_lab_api(self) -> None:
        import fruitfly_agent.lab as lab
        import fruitfly_agent.lab.tools as lab_tools

        self.assertFalse((ROOT / "fruitfly_agent" / "lab" / "tools" / "search.py").exists())
        self.assertFalse(hasattr(lab, "create_search_tool"))
        self.assertFalse(hasattr(lab, "install_search"))
        self.assertFalse(hasattr(lab_tools, "create_search_tool"))

    def test_ipython_agent_tool_adapter_lives_in_lab_tools(self) -> None:
        import fruitfly_agent.lab.context_manager.externalization.programmatic_context as rlm
        import fruitfly_agent.lab.tools as lab_tools

        tools = ROOT / "fruitfly_agent" / "lab" / "tools"
        rlm_root = ROOT / "fruitfly_agent" / "lab" / "rlm"
        self.assertTrue((tools / "ipython.py").is_file())
        self.assertFalse((rlm_root / "tool.py").exists())
        self.assertTrue(callable(lab_tools.create_ipython_tool))
        self.assertFalse(hasattr(rlm, "create_ipython_tool"))

    def test_lab_capabilities_are_grouped_by_runtime_responsibility(self) -> None:
        import fruitfly_agent.core as core

        information = ROOT / "fruitfly_agent" / "lab" / "context_manager" / "augmentation" / "information"
        self.assertFalse((information / "rolling_digest.py").exists())
        self.assertTrue((information / "pipeline.py").is_file())
        self.assertTrue((information / "hub.py").is_file())
        self.assertFalse((information / "sources.py").exists())
        for source in ("file_memory", "local_knowledge", "live_http"):
            self.assertTrue((information / source / "README.md").is_file())
            self.assertTrue((information / source / "source.py").is_file())
        self.assertFalse((information / "journal.py").exists())
        self.assertFalse((information / "memory_dream.py").exists())
        self.assertFalse((ROOT / "fruitfly_agent" / "lab" / "libraries").exists())
        self.assertFalse((ROOT / "fruitfly_agent" / "lab" / "adapters").exists())
        self.assertFalse((ROOT / "fruitfly_agent" / "lab" / "trajectory").exists())
        self.assertFalse((ROOT / "fruitfly_agent" / "lab" / "mechanisms").exists())
        self.assertTrue((information / "adapter.py").is_file())
        self.assertTrue((ROOT / "fruitfly_agent" / "lab" / "context_manager" / "reduction" / "README.md").is_file())
        self.assertFalse((ROOT / "fruitfly_agent" / "lab" / "tools" / "memory.py").exists())
        self.assertFalse(hasattr(core, "MemoryModule"))
        self.assertFalse(hasattr(core, "wire_memory"))
        self.assertFalse(hasattr(core, "TransformContextResult"))

    def test_context_pipeline_has_only_three_phases(self) -> None:
        from fruitfly_agent.core.context import ContextPipelineProfile
        from fruitfly_agent.core.mechanisms import MechanismContribution

        self.assertEqual(
            {"augmentation", "externalization", "reduction"},
            set(ContextPipelineProfile().to_dict()),
        )
        with self.assertRaisesRegex(ValueError, "unsupported context phase"):
            MechanismContribution("online", "context", "selection")

    def test_evidence_is_not_a_mechanism_layer(self) -> None:
        from fruitfly_agent.core.mechanisms import MechanismContribution

        with self.assertRaisesRegex(ValueError, "unsupported mechanism layer"):
            MechanismContribution("evidence", "workflow")

    def test_run_owns_configuration_and_lab_owns_mechanism_catalog(self) -> None:
        run = ROOT / "fruitfly_agent" / "run"
        self.assertTrue((run / "configuration" / "README.md").is_file())
        self.assertTrue((ROOT / "fruitfly_agent" / "lab" / "catalog" / "README.md").is_file())
        self.assertFalse((run / "catalog" / "builtins.py").exists())

    def test_interactive_frontend_has_module_documentation(self) -> None:
        interactive = ROOT / "fruitfly_agent" / "interactive"
        self.assertTrue((interactive / "README.md").is_file())

    def test_data_model_all_snapshot(self) -> None:
        import fruitfly_agent.core.data_model as data_model

        self.assertEqual(DATA_MODEL_PUBLIC_API, set(data_model.__all__))

    def test_env_public_surfaces_separate_contracts_and_implementations(self) -> None:
        import fruitfly_agent.core.env as core_env
        import fruitfly_agent.lab.environment as lab_env

        self.assertEqual(ENV_CONTRACT_PUBLIC_API, set(core_env.__all__))
        self.assertEqual(LAB_ENV_PUBLIC_API, set(lab_env.__all__))
        self.assertFalse(hasattr(core_env, "LocalEnv"))

    def test_core_all_snapshot(self) -> None:
        import fruitfly_agent.core as core

        self.assertEqual(CORE_PUBLIC_API, set(core.__all__))

    def test_root_reexports_core_surface(self) -> None:
        import fruitfly_agent
        import fruitfly_agent.core as core

        self.assertEqual(set(core.__all__), set(fruitfly_agent.__all__))

    def test_guarded_module_exports(self) -> None:
        import importlib

        for module_name, expected in MODULE_EXPORTS.items():
            module = importlib.import_module(module_name)
            public = (
                set(module.__all__)
                if hasattr(module, "__all__")
                else {n for n in dir(module) if not n.startswith("_")}
            )
            missing = expected - public
            self.assertEqual(set(), missing, f"{module_name} missing exports: {missing}")
