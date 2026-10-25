"""Container runtime staging preserves explicit immutable inputs only."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from eval.runtime import prepare_runtime
from eval.installation import installation_identity
from eval.contracts import EvaluationRequest


class RuntimeStagingTests(unittest.TestCase):
    def test_request_defaults_are_optional_but_explicit_empty_selections_are_rejected(self):
        payload = {"schema_version": 2, "benchmark": {"id": "terminal-bench", "variant": "smoke"}}
        request = EvaluationRequest.from_dict(payload)
        self.assertIsNone(request.runtime.config_path)
        self.assertIsNone(request.runtime.profile)
        self.assertEqual(request.runtime.working_directory, ".")
        self.assertEqual(EvaluationRequest.from_dict(request.to_dict()), request)
        for field in ("config_path", "profile", "working_directory"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                EvaluationRequest.from_dict({**payload, "runtime": {field: ""}})

    def fixture(self, root):
        state = root / ".fruitfly"
        state.mkdir()
        profile = {"model": {"catalog": "default-models.yaml", "profile": "main"},
            "mechanisms": [{"id": n} for n in ("local-env", "read-tool", "bash-tool", "compaction")]}
        (state / "default-config.yaml").write_text(yaml.safe_dump({"schema_version": 1,
            "default_profile": "baseline", "profiles": {"baseline": profile}}))
        spec = {"provider": "openai", "model": "fixture", "context_window": 32768,
                "max_output_tokens": 1024, "api_key_env": "SHARED_KEY"}
        (state / "default-models.yaml").write_text(yaml.safe_dump({"models": {
            "main": spec, "editor": {**spec, "api_key_env": "EDITOR_KEY"},
            "unselected": {**spec, "api_key_env": "UNRELATED_KEY"}}}))
        output = root / "staged"
        output.mkdir()
        return state, profile, output

    def test_defaults_are_independent_and_snapshots_exclude_unselected_keys_and_host_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, _, output = self.fixture(root)
            (state / "config.yaml").write_text("broken daily: [")
            (state / "permissions.yaml").write_text("broken host permissions: [")
            request = EvaluationRequest.from_dict({"schema_version": 2,
                "runtime": {"working_directory": str(root)}, "benchmark": {"id": "terminal-bench", "variant": "smoke"}})
            self.assertIsNone(request.runtime.config_path)
            config, models, names = prepare_runtime(runtime=request.to_dict()["runtime"], output_dir=output,
                environment={"SHARED_KEY": "fixture-not-a-real-key", "UNRELATED_KEY": "not-for-container"})
            self.assertEqual(names, ("SHARED_KEY",))
            self.assertEqual(set(yaml.safe_load(models.read_text())["models"]), {"main"})
            snapshot = json.loads((output / "runtime.json").read_text())
            self.assertEqual(snapshot["source"], "default")
            self.assertEqual(snapshot["profile"], "baseline")
            self.assertEqual(snapshot["execution_policy"], "unrestricted")
            self.assertFalse((output / "permissions.yaml").exists())
            self.assertEqual(set(snapshot["files"]), {"config.yaml", "models.yaml"})
            before = {p: p.read_bytes() for p in output.iterdir() if p.is_file()}
            (state / "default-models.yaml").write_text("modified afterwards")
            (state / "default-config.yaml").write_text("modified afterwards")
            for path, body in before.items():
                self.assertEqual(path.read_bytes(), body)
                self.assertNotIn(b"fixture-not-a-real-key", body)
                self.assertNotIn(b"not-for-container", body)
            normalized = yaml.safe_load(config.read_text())["profiles"]["baseline"]["mechanisms"]
            compaction = next(m for m in normalized if m["id"] == "compaction")
            self.assertIn("keep_recent_tokens", compaction["parameters"])

    def test_missing_default_fails_without_falling_back_and_credentials_are_checked_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, _, output = self.fixture(root)
            runtime = {"working_directory": str(root)}
            with self.assertRaisesRegex(ValueError, "missing evaluation credentials: SHARED_KEY"):
                prepare_runtime(runtime=runtime, output_dir=output, environment={})
            (state / "default-config.yaml").rename(state / "config.yaml")
            with self.assertRaises(FileNotFoundError):
                prepare_runtime(runtime=runtime, output_dir=output)
            config, _, _ = prepare_runtime(runtime={**runtime, "config_path": ".fruitfly/config.yaml"}, output_dir=output)
            self.assertTrue(config.is_file())
            self.assertEqual(json.loads((output / "runtime.json").read_text())["source"], "explicit")

    def test_declared_auxiliary_models_are_staged_without_unrelated_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, profile, output = self.fixture(root)
            profile["mechanisms"].append({"id": "component-improvement", "parameters": {"editor_profile": "editor"}})
            (state / "default-config.yaml").write_text(yaml.safe_dump({"schema_version": 1,
                "default_profile": "baseline", "profiles": {"baseline": profile}}))
            _, models, names = prepare_runtime(runtime={"working_directory": str(root)}, output_dir=output,
                environment={"SHARED_KEY": "fixture", "EDITOR_KEY": "fixture"})
            self.assertEqual(names, ("EDITOR_KEY", "SHARED_KEY"))
            self.assertEqual(set(yaml.safe_load(models.read_text())["models"]), {"main", "editor"})

    def test_explicit_execution_parameters_survive_the_real_container_staging_path(self):
        from fruitfly_agent.runtime_spec import load_harness_config, execution_kwargs
        from fruitfly_agent.core.config import AgentLoopConfig
        from tests.support.faux_provider import FauxProvider
        for limit in (0, 256):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state, profile, output = self.fixture(root)
                profile['execution'] = {'max_tool_calls_per_turn': limit, 'max_turns': 12,
                    'max_context_recovery_attempts': 3,
                    'tool_execution': {'max_parallel': 2, 'default_execution_mode': 'sequential'}}
                (state / 'default-config.yaml').write_text(yaml.safe_dump({'schema_version': 1,
                    'default_profile': 'baseline', 'profiles': {'baseline': profile}}))
                config, _, _ = prepare_runtime(runtime={'working_directory': str(root)}, output_dir=output)
                staged = load_harness_config(config).select()
                self.assertEqual(staged.execution, profile['execution'])
                loop = AgentLoopConfig(provider=FauxProvider(), **execution_kwargs(staged.execution))
                self.assertEqual(loop.max_tool_calls_per_turn, limit)
                self.assertEqual(loop.max_turns, 12)
                self.assertEqual(loop.tool_execution.max_parallel, 2)
                self.assertEqual(loop.tool_execution.default_execution_mode, 'sequential')

    def test_invalid_execution_parameters_fail_before_any_staging(self):
        for value in ({'max_tool_calls_per_turn': True}, {'max_turns': -1},
                      {'max_context_recovery_attempts': 0}, {'unknown': 2},
                      {'tool_execution': {'max_parallel': 0}},
                      {'tool_execution': {'default_execution_mode': 'unknown'}}, []):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state, profile, output = self.fixture(root)
                profile['execution'] = value
                (state / 'default-config.yaml').write_text(yaml.safe_dump({'schema_version': 1,
                    'default_profile': 'baseline', 'profiles': {'baseline': profile}}))
                with self.assertRaisesRegex(ValueError, 'execution'):
                    prepare_runtime(runtime={'working_directory': str(root)}, output_dir=output)
                self.assertEqual(list(output.iterdir()), [])

    def test_remote_execution_environment_is_rejected_before_container_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, profile, output = self.fixture(root)
            profile["mechanisms"] = [{"id": "ssh-env", "parameters": {"host": "fixture.invalid"}}]
            (state / "default-config.yaml").write_text(yaml.safe_dump({"schema_version": 1,
                "default_profile": "baseline", "profiles": {"baseline": profile}}))
            with self.assertRaisesRegex(ValueError, "inside the task container"):
                prepare_runtime(runtime={"working_directory": str(root)}, output_dir=output)

    def test_invalid_profile_shapes_and_credential_variables_fail_before_staging(self):
        for field, value, error in (("prompt", 1, "prompt"), ("artifact_bindings", [], "artifact bindings"),
                                    ("api_key_env", "KEY,UNRELATED", "environment variables")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state, profile, output = self.fixture(root)
                if field == "api_key_env":
                    path = state / "default-models.yaml"
                    models = yaml.safe_load(path.read_text())
                    models["models"]["main"][field] = value
                    path.write_text(yaml.safe_dump(models))
                else:
                    profile[field] = value
                    (state / "default-config.yaml").write_text(yaml.safe_dump({"schema_version": 1,
                        "default_profile": "baseline", "profiles": {"baseline": profile}}))
                with self.assertRaisesRegex(ValueError, error):
                    prepare_runtime(runtime={"working_directory": str(root)}, output_dir=output)
                self.assertEqual(list(output.iterdir()), [])

    def test_custom_prompt_and_component_content_are_verified_and_staged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / ".fruitfly/artifacts"
            artifacts.mkdir(parents=True)
            body = b"Use the configured instructions."
            digest = hashlib.sha256(body).hexdigest()
            (artifacts / digest).write_bytes(body)
            (artifacts / "unselected").write_text("private unrelated state")
            (root / "models.yaml").write_text("models: {fake: {provider: openai, model: fake, context_window: 8192, api_key_env: TEST_MODEL_KEY}}")
            reference = "sha256:" + digest
            config = root / "config.yaml"
            profile = {"model": {"catalog": "models.yaml", "profile": "fake"}, "mechanisms": [],
                       "prompt": reference, "artifact_bindings": {"configured-slot": reference}}
            config.write_text(yaml.safe_dump({"schema_version": 1, "default_profile": "default", "profiles": {"default": profile}}))
            output = root / "runtime"
            output.mkdir()
            generated, _, _ = prepare_runtime(runtime={"config_path": str(config), "profile": "default",
                                                       "working_directory": str(root)}, output_dir=output)
            staged = yaml.safe_load(generated.read_text())["profiles"]["default"]
            self.assertEqual(staged["prompt"], reference)
            self.assertEqual(staged["artifact_bindings"], profile["artifact_bindings"])
            self.assertEqual([p.name for p in (output / "artifacts").iterdir()], [digest])
            self.assertEqual((output / "artifacts" / digest).read_bytes(), body)
            (artifacts / digest).write_text("tampered")
            with self.assertRaisesRegex(ValueError, "content differs"):
                prepare_runtime(runtime={"config_path": str(config), "profile": "default",
                                         "working_directory": str(root)}, output_dir=output)

    def test_installation_identity_ignores_local_state_and_tracks_source_bytes(self):
        from eval.installation import SOURCE_FILES, SOURCE_PACKAGES
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in SOURCE_PACKAGES:
                (root / name).mkdir()
                (root / name / "__init__.py").write_text("")
            for name in SOURCE_FILES:
                (root / name).write_text("build input")
            (root / "pyproject.toml").write_text('[project]\nname="fruitfly-agent"\nversion="0.1"\n')
            first = installation_identity(root)
            (root / ".env").write_text("FIXTURE_ONLY=unrelated")
            self.assertEqual(first, installation_identity(root))
            (root / "fruitfly_agent/__init__.py").write_text("VERSION = '0.1'\n")
            self.assertNotEqual(first["sha256"], installation_identity(root)["sha256"])
