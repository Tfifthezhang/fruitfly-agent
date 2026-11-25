"""WorkBuddy dataset declarations composed with its isolated official execution backend."""
from pathlib import Path
import shutil
from typing import Any

from .base import BenchmarkDescriptor, BenchmarkVariant, PreflightResult
from fruitfly_eval.contracts import EvaluationRequest
from fruitfly_eval.backends.control import HarborControl
from fruitfly_eval.workbuddy.preparation import WorkBuddyPreparation, settings


class WorkBuddyCodeAdapter:
    descriptor = BenchmarkDescriptor('workbuddy-code', 'WorkBuddy Code',
        'Official WorkBuddy Code tasks with native FruitFlyAgent execution', '1.0', '1',
        (BenchmarkVariant('smoke', 'Single-task smoke', 'Validate one official Code task',
                          ('api_contract-hard-openapi_params',)),
         BenchmarkVariant('no_gpu', 'Tasks without GPU requirements', 'Exclude effective GPU resource requirements'),
         BenchmarkVariant('full', 'Full Code dataset', 'All resolved official Code tasks')),
        ('success_rate', 'official_reward', 'error_rate', 'timeout_rate', 'input_tokens',
         'output_tokens', 'cost_usd', 'latency_ms'), 'wb-bench-code-v1.0',
        {'provider': True, 'control_plane': True, 'task_environment': True, 'verifier': True},
        'harbor_task_container', 'api_contract-hard-openapi_params')

    def __init__(self) -> None:
        self.host_config_path: str | None = None

    @property
    def preparation(self) -> WorkBuddyPreparation:
        return WorkBuddyPreparation()

    @property
    def control(self) -> HarborControl:
        return HarborControl()

    def configure_host(self, path: str) -> None:
        self.host_config_path = path

    def initial_files(self) -> dict[str, str]:
        from importlib.resources import files
        resources = files('fruitfly_eval.workbuddy').joinpath('templates')
        return {'eval-host.yaml': resources.joinpath('eval-host.yaml').read_text(),
                'workbuddy-runner.yaml': resources.joinpath('runner.yaml').read_text()}

    def preflight(self, variant: str) -> PreflightResult:
        if variant not in {v.variant_id for v in self.descriptor.variants}:
            return PreflightResult(False, ({'id': 'variant', 'ok': False, 'detail': 'unknown WorkBuddy variant'},))
        try:
            host = self.preparation.read_host(Path.cwd(), self.host_config_path)
            runner = settings(host)
            executable = runner.python.with_name('harbor')
            checks = ({'id': 'workbuddy_runner', 'ok': executable.is_file(),
                       'detail': 'Isolated runner is configured; prepare validates installed engine and environments'},
                      {'id': 'docker', 'ok': bool(shutil.which('docker')), 'detail': 'Docker CLI availability'})
            return PreflightResult(all(c['ok'] for c in checks), checks, (str(executable),))
        except (OSError, ValueError, KeyError) as exc:
            return PreflightResult(False, ({'id': 'workbuddy_runner', 'ok': False, 'detail': str(exc)},))

    def run(self, *, request_path: Path, result_path: Path, variant: str, progress: Any = None) -> None:
        request = EvaluationRequest.read(request_path)
        if request.benchmark.benchmark_id != self.descriptor.benchmark_id or request.benchmark.variant != variant:
            raise ValueError('WorkBuddy request differs from its registered benchmark selection')
        host = self.preparation.read_host(Path(request.runtime.working_directory), self.host_config_path)
        from fruitfly_eval.workbuddy.runner import run
        run(request, self.descriptor, host, result_path, progress=progress)
