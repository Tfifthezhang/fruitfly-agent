"""Runner source identity excludes secrets and rejects unreviewed source drift."""
from pathlib import Path
import tempfile
import unittest
import yaml
from fruitfly_eval.workbuddy.configuration import RunnerSettings, runner_identity


class WorkBuddyConfigurationTests(unittest.TestCase):
    def test_runner_resource_identity_and_strict_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / 'upstream'; checkout.mkdir()
            (checkout / 'pyproject.toml').write_text('[tool.uv.sources]\nharbor={tag="v0.18.0"}\n')
            (checkout / 'uv.lock').write_text('fixture lock')
            for path in ('src/workbuddy_bench', 'configs/bench'):
                (checkout / path).mkdir(parents=True)
                (checkout / path / 'fixture').write_text('runtime resource')
            original = runner_identity(checkout)
            (checkout / '.env').write_text('PRIVATE_FIXTURE_ONLY=first')
            (checkout / 'results').mkdir()
            (checkout / 'results/output').write_text('new execution')
            self.assertEqual(runner_identity(checkout), original)
            executable = root / 'python'; executable.write_text('fixture executable')
            path = root / 'runner.yaml'
            payload = {'checkout': 'upstream', 'python': 'python', 'source_sha256': original['source_sha256']}
            path.write_text(yaml.safe_dump(payload))
            config = RunnerSettings.read(path)
            self.assertEqual(config.validate(), original)
            path.write_text(yaml.safe_dump(config.to_dict()))
            self.assertEqual(RunnerSettings.read(path).validate(), original)
            (checkout / 'src/workbuddy_bench/fixture').write_text('drift')
            with self.assertRaisesRegex(ValueError, 'differs'):
                config.validate()
            path.write_text(yaml.safe_dump({**payload, 'api_key': 'FORBIDDEN_FIXTURE'}))
            with self.assertRaisesRegex(ValueError, 'fields'):
                RunnerSettings.read(path)
