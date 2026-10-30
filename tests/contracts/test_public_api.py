"""Public exports and source responsibility invariants."""
import unittest
from tests.contracts.api_baseline import CORE_PUBLIC_API, DATA_MODEL_PUBLIC_API, ENV_CONTRACT_PUBLIC_API, LAB_ENV_PUBLIC_API, LAB_HOST_PUBLIC_API, MODULE_EXPORTS

class PublicApiTest(unittest.TestCase):
    def test_host_and_orchestration_exports_have_explicit_owners(self):
        from fruitfly_agent.lab.improvement import api
        from fruitfly_agent.improvement.contracts import pipeline
        from fruitfly_agent.core import config
        self.assertEqual(LAB_HOST_PUBLIC_API, set(api.__all__))
        self.assertEqual({'ImprovementOutcome', 'WorkflowController', 'experience_id'}, set(pipeline.__all__))
        self.assertEqual({'AgentLoopConfig', 'ToolExecutionConfig'}, set(config.__all__))

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
