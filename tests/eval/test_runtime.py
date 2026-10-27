"""Container runtime staging preserves explicit immutable inputs only."""
from tests.support.configuration import profile_document, component_document
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from eval.runtime import prepare_runtime
from eval.installation import installation_identity
from eval.contracts import EvaluationRequest
from fruitfly_agent.lab.catalog import load_system_config


class RuntimeStagingTests(unittest.TestCase):
    def test_staging_preserves_service_request_and_transport_settings(self):
        from fruitfly_agent.providers.registry import load_model_specs
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, _, output = self.fixture(root)
            path = state / 'models.yaml'
            models = yaml.safe_load(path.read_text())
            models['models']['main'].update(service='deepseek', model='deepseek-flash',
                parameters={'reasoning': {'effort': 'high'}}, transport={'total_timeout': 321})
            path.write_text(yaml.safe_dump(models))
            _, staged_path, _ = prepare_runtime(runtime={'working_directory': str(root)}, output_dir=output)
            staged = load_model_specs(staged_path)['main']
            self.assertEqual(staged.service, 'deepseek')
            self.assertEqual(staged.parameters, {'reasoning': {'effort': 'high'}})
            self.assertEqual(staged.transport, {'total_timeout': 321})
    def test_request_defaults_are_optional_but_explicit_empty_selections_are_rejected(self):
        payload = {"benchmark": {"id": "terminal-bench", "variant": "smoke"}}
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
        profile = profile_document(catalog="models.yaml", executor="main", mechanisms=[{"id": n} for n in ("local-env", "read-tool", "bash-tool", "compaction")])
        (state / "default-config.yaml").write_text(yaml.safe_dump({
            "default_profile": "baseline", "profiles": {"baseline": profile}}))
        spec = {'sdk': 'openai', 'protocol': 'responses', "model": "fixture", "context_window": 32768,
                "max_output_tokens": 1024, "api_key_env": "SHARED_KEY"}
        (state / "models.yaml").write_text(yaml.safe_dump({"models": {
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
            request = EvaluationRequest.from_dict({
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
            (state / "models.yaml").write_text("modified afterwards")
            (state / "default-config.yaml").write_text("modified afterwards")
            for path, body in before.items():
                self.assertEqual(path.read_bytes(), body)
                self.assertNotIn(b"fixture-not-a-real-key", body)
                self.assertNotIn(b"not-for-container", body)
            normalized = [item.to_dict() for item in load_system_config(config).select().mechanisms]
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
            profile['models']['roles']['editor'] = 'editor'
            profile['I']['component-improvement'] = component_document('component-improvement')
            (state / "default-config.yaml").write_text(yaml.safe_dump({
                "default_profile": "baseline", "profiles": {"baseline": profile}}))
            _, models, names = prepare_runtime(runtime={"working_directory": str(root)}, output_dir=output,
                environment={"SHARED_KEY": "fixture", "EDITOR_KEY": "fixture"})
            self.assertEqual(names, ("EDITOR_KEY", "SHARED_KEY"))
            self.assertEqual(set(yaml.safe_load(models.read_text())["models"]), {"main", "editor"})

    def test_component_staging_preserves_i_and_inactive_role_metadata_without_requesting_its_key(self):
        from fruitfly_agent.lab.catalog import load_system_config
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, _, output = self.fixture(root)
            def component(name, role, parameters):
                return {'inline': {'id': name, 'role': role,
                    'implementation': name, 'parameters': parameters}}
            (state / 'default-config.yaml').write_text(yaml.safe_dump({
                'default_profile': 'baseline', 'profiles': {'baseline': {
                    'models': {'catalog': 'models.yaml', 'roles': {
                        'executor': 'main', 'editor': 'editor', 'assessor': 'editor'}},
                    'H': {'execution-policy': component('execution-policy', 'H', {'max_tool_calls_per_turn': 128}),
                          'base_prompt': component('base_prompt', 'H', {'text': 'Exact prompt.\n'})},
                    'I': {'improvement-feedback': component('improvement-feedback', 'I', {
                        'evidence': {'page_characters': 23}, 'judgment_guidance': 'Inspect loops.'}),
                          'improvement-search': component('improvement-search', 'I', {'rounds': 2})}}}}))
            generated, models, names = prepare_runtime(runtime={'working_directory': str(root)},
                output_dir=output, environment={'SHARED_KEY': 'fixture'})
            staged = load_system_config(generated).select()
            self.assertNotIn('schema_version', yaml.safe_load(generated.read_text()))
            self.assertEqual(staged.component_settings['feedback']['evidence']['page_characters'], 23)
            self.assertEqual(staged.component_settings['feedback']['judgment_guidance'], 'Inspect loops.')
            self.assertEqual(staged.component_settings['search']['rounds'], 2)
            self.assertEqual(staged.execution['max_tool_calls_per_turn'], 128)
            self.assertEqual(staged.artifact_contents[staged.prompt], 'Exact prompt.\n')
            self.assertEqual(staged.model_roles['editor'], 'editor')
            self.assertEqual(set(yaml.safe_load(models.read_text())['models']), {'main', 'editor'})
            self.assertEqual(names, ('SHARED_KEY',))

    def test_explicit_execution_parameters_survive_the_real_container_staging_path(self):
        from fruitfly_agent.runtime_spec import execution_kwargs
        from fruitfly_agent.core.config import AgentLoopConfig
        from tests.support.faux_provider import FauxProvider
        for limit in (0, 256):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state, profile, output = self.fixture(root)
                execution = {'max_tool_calls_per_turn': limit, 'max_turns': 12,
                    'max_context_recovery_attempts': 3,
                    'tool_execution': {'max_parallel': 2, 'default_execution_mode': 'sequential'}}
                profile['H']['execution-policy'] = {'inline': {'id': 'execution-policy',
                    'role': 'H', 'implementation': 'execution-policy', 'parameters': execution}}
                (state / 'default-config.yaml').write_text(yaml.safe_dump({
                    'default_profile': 'baseline', 'profiles': {'baseline': profile}}))
                config, _, _ = prepare_runtime(runtime={'working_directory': str(root)}, output_dir=output)
                staged = load_system_config(config).select()
                self.assertEqual(staged.execution, execution)
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
                profile['H']['execution-policy']['inline']['parameters'] = value
                (state / 'default-config.yaml').write_text(yaml.safe_dump({
                    'default_profile': 'baseline', 'profiles': {'baseline': profile}}))
                with self.assertRaisesRegex(ValueError, 'execution'):
                    prepare_runtime(runtime={'working_directory': str(root)}, output_dir=output)
                self.assertEqual(list(output.iterdir()), [])

    def test_remote_execution_environment_is_rejected_before_container_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state, profile, output = self.fixture(root)
            profile['H'] = {'ssh-env': component_document('ssh-env', parameters={'host': 'fixture.invalid'})}
            (state / "default-config.yaml").write_text(yaml.safe_dump({
                "default_profile": "baseline", "profiles": {"baseline": profile}}))
            with self.assertRaisesRegex(ValueError, "inside the task container"):
                prepare_runtime(runtime={"working_directory": str(root)}, output_dir=output)

    def test_invalid_profile_shapes_and_credential_variables_fail_before_staging(self):
        for field, value, error in (("prompt", 1, "unknown fields"), ("artifact_bindings", [], "unknown fields"),
                                    ("api_key_env", "KEY,UNRELATED", "environment variables")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state, profile, output = self.fixture(root)
                if field == "api_key_env":
                    path = state / "models.yaml"
                    models = yaml.safe_load(path.read_text())
                    models["models"]["main"][field] = value
                    path.write_text(yaml.safe_dump(models))
                else:
                    profile[field] = value
                    (state / "default-config.yaml").write_text(yaml.safe_dump({
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
            (root / "models.yaml").write_text('models: {fake: {sdk: openai, protocol: responses, model: fake, context_window: 8192, api_key_env: TEST_MODEL_KEY}}')
            reference = "sha256:" + digest
            config = root / "config.yaml"
            profile = profile_document(catalog="models.yaml", executor="fake",
                mechanisms=[{'id': 'local-env'}, {'id': 'read-tool'}], prompt=reference,
                artifact_bindings={'tool-guidance.read': reference},
                artifact_reader=lambda value: (artifacts / value[7:]).read_text())
            config.write_text(yaml.safe_dump({"default_profile": "default", "profiles": {"default": profile}}))
            output = root / "runtime"
            output.mkdir()
            generated, _, _ = prepare_runtime(runtime={"config_path": str(config), "profile": "default",
                                                       "working_directory": str(root)}, output_dir=output)
            staged = load_system_config(generated).select()
            self.assertEqual(staged.prompt, reference)
            self.assertEqual(staged.artifact_bindings['tool-guidance.read'], reference)
            self.assertEqual([p.name for p in (output / "artifacts").iterdir()], [digest])
            self.assertEqual((output / "artifacts" / digest).read_bytes(), body)
            (artifacts / digest).write_text("tampered")
            # The authored component contains the frozen text; the old artifact
            # store is no longer an input. Conflicting component values still fail.
            profile['H']['read-tool']['inline']['artifacts']['tool-guidance.read'] = 'tampered'
            config.write_text(yaml.safe_dump({'default_profile': 'default', 'profiles': {'default': profile}}))
            with self.assertRaisesRegex(ValueError, "conflicting configured artifact"):
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
