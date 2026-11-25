"""Official-shaped WorkBuddy material and explicit offline engine responses."""
from pathlib import Path
import sys
import tomllib
import yaml

from fruitfly_eval.harbor.host import HostConfig
from fruitfly_eval.workbuddy.configuration import runner_identity
from tests.support.experiments import workspace


def fixture(root: Path):
    workspace(root)
    checkout = root / 'workbuddy'
    (checkout / 'src/workbuddy_bench').mkdir(parents=True)
    (checkout / 'src/workbuddy_bench/__init__.py').write_text('# fixture source')
    (checkout / 'configs/bench').mkdir(parents=True)
    (checkout / 'configs/bench/_default.yaml').write_text('environment: {type: docker}\n')
    (checkout / 'pyproject.toml').write_text('[tool.uv.sources]\nharbor={tag="v0.18.0"}\n')
    (checkout / 'uv.lock').write_text('offline fixture lock')
    runner = root / 'runner.yaml'
    runner.write_text(yaml.safe_dump({'checkout': str(checkout), 'python': sys.executable,
                                    'source_sha256': runner_identity(checkout)['source_sha256']}))
    dataset = root / 'wb-bench-code-v1.0'
    (dataset / 'shared/verifier').mkdir(parents=True)
    (dataset / 'shared/verifier/plugin.py').write_text('# official-shaped verifier fixture')
    (dataset / 'dataset.toml').write_text('[dataset]\nid="wb-bench-code-v1.0"\n[verifier]\nengine="composite"\n')
    for name in ('first', 'second'):
        task = dataset / 'tasks' / name
        (task / 'tests').mkdir(parents=True)
        (task / 'tests/test.sh').write_text('# fixture rule')
        (task / 'task.toml').write_text('[task]\nname="workbuddy/' + name + '"\n[environment]\ndocker_image="fixture/code:v1"\n')
        (task / 'instruction.md').write_text('Implement ' + name)
    runtime = root / 'runtime'; runtime.mkdir()
    (runtime / 'fixture').write_text('mounted Python fixture')
    path = root / 'host.yaml'
    path.write_text(yaml.safe_dump({'cache': str(root / 'cache'), 'task_directory': str(dataset),
        'agent': {'python': '/runtime/bin/python', 'mounts': [{'source': str(runtime), 'target': '/runtime'}]},
        'backend': {'file': str(runner)}}))
    return HostConfig.read(root, path)


class Engine:
    def __init__(self):
        self.calls = []

    def call(self, operation, payload, **kwargs):
        self.calls.append((operation, payload))
        if operation == 'describe':
            return {'controller': {'python': 'fixture', 'packages': {'harbor': '0.18.0'}},
                    'engine': {'harbor': '0.18.0', 'sha256': 'fixture-engine-source'}}
        if operation == 'bench':
            return {'bench': {'environment': {'type': 'docker'}, 'agent_user': 'dev',
                              'verifier_user': 'dev', 'timeout_multiplier': 2.5}}
        if operation == 'normalize':
            return {'contract_changes': 0, 'user_changes': 0}
        if operation == 'resources':
            rows = {}
            for value in payload['tasks']:
                path = Path(value)
                config = tomllib.loads((path / 'task.toml').read_text())
                rows[str(path.resolve())] = {'gpu_requirements': [], 'builds': [],
                    'images': [{'reference': config['environment']['docker_image']}]}
            return {'resources': rows}
        if operation == 'probe':
            return {'images': [{'reference': 'fixture/code:v1', 'id': 'sha256:fixture'}]}
        if operation == 'validate_job':
            return {'valid': True}
        raise AssertionError(operation)

    def environment(self, values=None):
        return dict(values or {})
