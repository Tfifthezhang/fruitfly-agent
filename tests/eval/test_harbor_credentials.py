"""Harbor credentials behavior and failure contracts."""
from __future__ import annotations
from tests.support.configuration import profile_document
import json
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
import yaml
from fruitfly_eval.runtime import prepare_runtime
from fruitfly_eval.benchmarks.swe_bench import SWEBenchAdapter
from fruitfly_eval.benchmarks.base import PreflightResult
from fruitfly_agent.lab.catalog import MechanismDefinition, MechanismDescriptor, MechanismContribution, builtin_catalog
from tests.support.evaluation import request_payload
from tests.support.harbor import load_harbor_agent, prepared_harbor


FruitFlyHarborAgent = load_harbor_agent()


class HarborAdapterTests(unittest.TestCase):
    def test_runner_reads_new_workspace_secrets_without_merging_legacy_file(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (root / ".fruitfly").mkdir()
        (root / ".env").write_text("LEGACY_ONLY=old\nTEST_API_KEY=old-placeholder\n")
        (root / ".fruitfly/secrets.env").write_text("NEW_ONLY=present\nTEST_API_KEY=new-placeholder\n")
        request = root / "request.json"
        payload = request_payload()
        payload["runtime"]["working_directory"] = str(root)
        request.write_text(json.dumps(payload))
        adapter = SWEBenchAdapter()
        host, preparation = prepared_harbor(root)
        with patch.dict("os.environ", {"TEST_API_KEY": "process-placeholder"}, clear=True), patch.object(
            adapter, "preflight", return_value=PreflightResult(True, (), ("offline-harbor",))
        ), patch("fruitfly_eval.benchmarks.harbor.prepare_runtime", return_value=(root / "config", root / "models", ("TEST_API_KEY",))), patch(
            "fruitfly_eval.benchmarks.harbor.run_harbor_job", return_value=(1, "offline stop")
        ) as job, patch("sys.stderr"), patch(
            "fruitfly_eval.benchmarks.harbor.HostConfig.read", return_value=host
        ), patch("fruitfly_eval.benchmarks.harbor.load_preparation", return_value=preparation), patch(
            "fruitfly_eval.benchmarks.harbor.inspect_preparation", return_value={"available": True}):
            with self.assertRaisesRegex(RuntimeError, "offline stop"):
                adapter.run(request_path=request, result_path=root / "result.json", variant="smoke")
        env = job.call_args.kwargs["environment"]
        self.assertEqual(env["TEST_API_KEY"], "process-placeholder")
        self.assertEqual(env["NEW_ONLY"], "present")
        self.assertNotIn("LEGACY_ONLY", env)

    def test_selected_config_is_copied_with_its_enabled_mechanisms(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.yaml"
            models_path = root / "models.yaml"
            config_path.write_text(yaml.safe_dump({'default_profile': 'default', 'profiles': {
                'default': profile_document(catalog='models.yaml', executor='test',
                    mechanisms=[{'id': 'context-history'}, {'id': 'working-memory-reduction', 'enabled': True, 'parameters': {}}])}}))
            models_path.write_text(
                'models:\n  test:\n    sdk: openai\n    protocol: responses\n    api_key_env: TEST_API_KEY\n    model: test-model\n    context_window: 8192\n    max_output_tokens: 1024\n',
                encoding="utf-8",
            )
            output = root / "runtime"
            output.mkdir()
            generated, copied_models, secret_names = prepare_runtime(
                runtime={"config_path": str(config_path), "profile": "default"},
                output_dir=output,
            )
            payload = yaml.safe_load(generated.read_text(encoding="utf-8"))
            from fruitfly_agent.lab.catalog import load_system_config
            profile = load_system_config(generated).select()
            enabled = {item.mechanism_id: item.enabled for item in profile.mechanisms}
            self.assertEqual(
                profile.model_catalog,
                "/installed-agent/fruitfly/runtime/models.yaml",
            )
            self.assertEqual(enabled, {"context-history": True, "working-memory-reduction": True})
            copied = yaml.safe_load(copied_models.read_text())["models"]["test"]
            self.assertEqual(copied["model"], "test-model")
            self.assertEqual(copied["api_key_env"], "TEST_API_KEY")
            self.assertEqual(copied["max_output_tokens"], 1024)
            self.assertEqual(secret_names, ("TEST_API_KEY",))

    def test_runtime_forwards_independent_web_secrets_with_defaults_and_overrides(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (root / "models.yaml").write_text(yaml.safe_dump({"models": {
            "test": {'sdk': 'openai', 'protocol': 'responses', "model": "fake", "context_window": 8192, "api_key_env": "MODEL_KEY"}}}))
        for backend, search_key, fetch_key, expected in (
            ("deepseek", "", "", {"DEEPSEEK_SEARCH_API_KEY", "DEEPSEEK_FETCH_API_KEY"}),
            ("deepseek", "SEARCH_ONLY", "FETCH_ONLY", {"SEARCH_ONLY", "FETCH_ONLY"}),
            ("deepseek", "MODEL_KEY", "MODEL_KEY", set()),
            ("brave", "", "", {"BRAVE_SEARCH_API_KEY"}),
            ("deepseek", "DISABLED_KEY", "", {"DEEPSEEK_FETCH_API_KEY"}),
        ):
            with self.subTest(backend=backend, search_key=search_key):
                mechanisms = [
                    {"id": "web-search-tool", "enabled": search_key != "DISABLED_KEY", "parameters": {'backend': backend, 'api_key_env': search_key}},
                    {"id": "web-fetch-tool", "parameters": {'backend': 'deepseek' if backend == 'deepseek' else 'direct', 'api_key_env': fetch_key}},
                ]
                config = root / "config.yaml"
                config.write_text(yaml.safe_dump({"default_profile": "default", "profiles": {"default": profile_document(catalog="models.yaml", mechanisms=mechanisms)}}))
                output = root / "runtime"
                output.mkdir(exist_ok=True)
                generated, _, names = prepare_runtime(
                    runtime={"config_path": str(config), "profile": "default"}, output_dir=output)
                self.assertEqual(expected | {"MODEL_KEY"}, set(names))
                self.assertNotIn("DISABLED_KEY", names)
                from fruitfly_agent.lab.catalog import load_system_config
                staged = {item.mechanism_id: item.to_dict() for item in load_system_config(generated).select().mechanisms}
                self.assertEqual({m['id'] for m in mechanisms}, set(staged))
                for original in mechanisms:
                    copied = staged[original['id']]
                    self.assertEqual(copied["enabled"], original.get("enabled", True))
                    for key, value in original.get("parameters", {}).items():
                        self.assertEqual(copied["parameters"][key], value)

    def test_runtime_collects_non_web_component_credentials_through_catalog(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (root / "models.yaml").write_text('models: {test: {sdk: openai, protocol: responses, model: fake, context_window: 8192, api_key_env: MODEL_KEY}}')
        definition = MechanismDefinition(
            MechanismDescriptor("fixture-resource", "Fixture resource", "Fixture credential consumer.",
                                contributions=(MechanismContribution("capability", "tools"),)),
            lambda *args: self.fail("credential discovery ran an installer"),
            credential_variables=lambda parameters: ("RESOURCE_KEY",),
            implementation_path="tests/eval/test_harbor_credentials.py", documentation_path="tests/eval/README.md")
        catalog = builtin_catalog().extended((definition,))
        (root / 'config.yaml').write_text(yaml.safe_dump({'default_profile': 'default', 'profiles': {
            'default': profile_document(catalog='models.yaml', mechanisms=[{'id': 'fixture-resource'}], lab=catalog)}}))
        (root / "runtime").mkdir()
        with patch("fruitfly_eval.runtime.builtin_catalog", return_value=catalog):
            _, _, names = prepare_runtime(runtime={"config_path": str(root / "config.yaml"), "profile": "default"},
                                         output_dir=root / "runtime")
        self.assertEqual(("MODEL_KEY", "RESOURCE_KEY"), names)
