"""Resolve benchmark references and derive bounded hosts without editing originals."""
from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
from typing import Any
import yaml

from eval.api import EvaluationRequest
from eval.harbor.host import HostConfig
from fruitfly_agent.runtime_spec import runtime_reference


@dataclass(frozen=True)
class BenchmarkSettings:
    request: EvaluationRequest
    source_request: Path
    host: HostConfig
    generated_host: Path
    host_bytes: bytes
    model_calls: int

    def stage_host(self):
        self.generated_host.parent.mkdir(parents=True, exist_ok=True)
        if self.generated_host.exists():
            if self.generated_host.read_bytes() != self.host_bytes:
                raise ValueError('derived benchmark host was modified; remove the corrupt derived file')
        else:
            self.generated_host.write_bytes(self.host_bytes)
        return self.generated_host

    def require_host(self):
        if not self.generated_host.is_file() or self.generated_host.read_bytes() != self.host_bytes:
            raise ValueError('bounded benchmark host is not prepared; run fruitfly-agent-lab eval prepare')
        return self.generated_host


def resolve_benchmark(config):
    task = config.task
    if set(task) - {'source', 'request', 'host', 'model_calls'}:
        raise ValueError('unknown Eval task settings')
    request_path = config.resolve(task['request']) if 'request' in task else config.workspace / '.fruitfly/eval-request.json'
    request = EvaluationRequest.read(request_path)
    workspace = Path(request.runtime.working_directory)
    workspace = (workspace if workspace.is_absolute() else config.workspace / workspace).resolve()
    if workspace != config.workspace:
        raise ValueError('Eval request and experiment must use the same workspace; select it with --cwd')
    baseline, profile = runtime_reference(workspace, request.runtime.config_path, request.runtime.profile,
        inherited_path=config.resolve(config.runtime['config']) if 'config' in config.runtime else None,
        inherited_profile=config.runtime.get('profile'))
    request = replace(request, runtime=replace(request.runtime, working_directory=str(workspace),
        config_path=str(baseline), profile=profile))
    host_path = config.resolve(task['host']) if 'host' in task else None
    host = HostConfig.read(workspace, host_path)
    model_calls = task.get('model_calls', 80)
    if type(model_calls) is not int or not 1 <= model_calls <= 10000:
        raise ValueError('task.model_calls must be an integer between 1 and 10000')
    payload: dict[str, Any] = {'schema_version': 1, 'cache': str(host.cache),
        'agent': {'python': host.python,
            'mounts': [{'source': str(m.source), 'target': m.target} for m in host.mounts],
            'library_paths': list(host.library_paths)},
        'environment': {'setup': dict(host.setup_env),
            'agent': {**host.agent_env, 'FRUITFLY_MAX_MODEL_CALLS': str(model_calls)},
            'verifier': dict(host.verifier_env)},
        'dependencies': {'assets': list(host.assets), 'prepare': list(host.preparation), 'offline': host.offline},
        'task_patches': list(host.task_patches)}
    if host.task_directory:
        payload['task_directory'] = str(host.task_directory)
    if host.uv:
        payload['dependencies']['uv'] = host.uv
    data = yaml.safe_dump(payload, sort_keys=False).encode()
    identity = hashlib.sha256(data).hexdigest()
    generated = workspace / '.fruitfly/experiments/prepared' / identity / 'host.yaml'
    return BenchmarkSettings(request, request_path, host, generated, data, model_calls)
