"""Run the official engine with native Agent configuration and common lifecycle receipts."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
from typing import Any

import yaml
from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.workspace import WorkspacePaths
from fruitfly_eval.bridges.model_access import configure_model_access, configure_model_network
from fruitfly_eval.contracts import EvaluationRequest, RESULT_SCHEMA_VERSION
from fruitfly_eval.harbor.dependencies import dependency_environment, dependency_mounts
from fruitfly_eval.harbor.host import HostConfig
from fruitfly_eval.harbor.material import runtime_mounts, write_json
from fruitfly_eval.harbor.tasks import validate_coverage, coverage_report
from fruitfly_eval.runtime import prepare_runtime
from fruitfly_eval.runner import run_harbor_job
from fruitfly_eval.task_selection import select_prepared_tasks
from .preparation import WorkBuddyPreparation, settings, engine

AGENT_IMPORT = 'fruitfly_eval.workbuddy.agent:WorkBuddyFruitFlyAgent'
ENVIRONMENT_IMPORT = 'fruitfly_eval.workbuddy.environment:PreparedWorkBuddyEnvironment'


def job_configuration(request: EvaluationRequest, host: HostConfig, receipt: dict[str, Any], *,
                      root: Path, config: Path, models: Path, profile: str, secrets: tuple[str, ...],
                      relay_directory: Path, relay_required: bool) -> dict[str, Any]:
    result = deepcopy(receipt['bench'])
    for field in ('agent_user', 'verifier_user', 'context_window', 'context_compact_pct',
                  'llm_judge', 'llm_judge_override', 'verifier_env_from_judge'):
        result.pop(field, None)
    environment = result.setdefault('environment', {})
    environment.update(type='docker', import_path=ENVIRONMENT_IMPORT)
    environment['mounts'] = [*environment.get('mounts', []), *runtime_mounts(receipt['runtime'])]
    environment.setdefault('kwargs', {})['dependency_mounts'] = dependency_mounts(host)
    environment['env'] = {**environment.get('env', {}), **dependency_environment(host), **host.setup_env}
    agent = {'import_path': AGENT_IMPORT, 'kwargs': {'config_path': str(config),
        'model_catalog_path': str(models), 'profile': profile, 'secret_names': ','.join(secrets)}}
    configure_model_access(environment, agent, required=relay_required,
                           directory=relay_directory, settings=dict(host.model_relay))
    configure_model_network(agent, models)
    verifier = result.setdefault('verifier', {})
    verifier['env'] = {**verifier.get('env', {}), **dependency_environment(host), **host.verifier_env}
    result.update(job_name='workbuddy', jobs_dir=str(root), n_attempts=request.execution.attempts,
        n_concurrent_trials=request.execution.concurrency, retry={'max_retries': 0},
        agents=[agent], tasks=[{'path': t['path'], 'source': receipt['dataset']} for t in receipt['tasks']], datasets=[])
    return result


def run(request: EvaluationRequest, descriptor: Any, host: HostConfig, result_path: Path, *, progress=None) -> None:
    backend = WorkBuddyPreparation()
    receipt = backend.load(host, descriptor, request.benchmark.variant)
    readiness = backend.inspect(request, descriptor, host, receipt=receipt)
    if not readiness['available']:
        raise ValueError('WorkBuddy preparation check failed: ' + json.dumps(readiness['checks']))
    receipt = select_prepared_tasks(receipt, request.benchmark.task_names)
    root = result_path.parent / 'harbor'
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / 'preparation.json', receipt)
    write_json(root / 'readiness.json', readiness)
    runner = settings(host)
    client = engine(host, source=Path(receipt['runtime']['source']))
    environment = client.environment({**load_env(WorkspacePaths(Path(request.runtime.working_directory)).secret_file()), **os.environ})
    config, models, secrets = prepare_runtime(runtime=asdict(request.runtime), output_dir=root,
        environment=environment, model_relay=True)
    runtime = json.loads((root / 'runtime.json').read_text())
    with tempfile.TemporaryDirectory(prefix='ffrelay-') as relay:
        job = job_configuration(request, host, receipt, root=root, config=config, models=models,
            profile=runtime['profile'], secrets=secrets, relay_directory=Path(relay),
            relay_required=bool(runtime['connected_models']))
        path = root / 'harbor-job.yaml'
        path.write_text(yaml.safe_dump(job, sort_keys=False))
        from .results import measurement_plan
        write_json(root / 'measurement-plan.json', measurement_plan(receipt, runtime,
            config_path=config, models_path=models, attempts=request.execution.attempts,
            execution=asdict(request.execution)))
        # Validate the composed official-engine schema before task execution.
        client.call('validate_job', {'checkout': str(runner.checkout), 'job': job})
        executable = runner.python.with_name('harbor')
        if not executable.is_file():
            raise ValueError('isolated runner has no Harbor CLI beside its Python')
        command = [str(executable), 'run', '--config', str(path), '--yes',
                   '--plugin', 'fruitfly_eval.workbuddy.hooks:WorkBuddyEvidencePlugin']
        errors: dict[str, str] = {}
        try:
            code, detail = run_harbor_job(command, environment=environment,
                timeout=request.execution.timeout_seconds, job_root=root, progress=progress,
                job_id='workbuddy', docker='docker')
            if code:
                errors['runner'] = 'WorkBuddy engine exited with ' + str(code) + ': ' + detail[-2000:]
        except (RuntimeError, KeyboardInterrupt) as exc:
            errors['runner'] = str(exc) or 'execution interrupted'
        from .results import read_results
        trials, metrics = [], []
        try:
            trials, metrics = read_results(root / 'workbuddy/result.json', receipt, runtime,
                                          config_path=config, models_path=models)
            validate_coverage(receipt['tasks'], trials, request.execution.attempts)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            errors['results'] = str(exc)
            metrics = []
        coverage = coverage_report(receipt['tasks'], trials, request.execution.attempts)
        write_json(result_path, {'schema_version': RESULT_SCHEMA_VERSION,
            'status': 'failed' if errors else 'completed', 'metrics': metrics, 'trials': trials,
            'errors': errors, 'coverage': coverage, 'runtime_snapshot': runtime,
            'artifacts': [{'kind': 'harbor_job', 'path': str(root / 'workbuddy')},
                {'kind': 'preparation', 'path': str(root / 'preparation.json')},
                {'kind': 'runtime_snapshot', 'path': str(root / 'runtime.json')},
                {'kind': 'workbuddy_job', 'path': str(path)},
                {'kind': 'readiness', 'path': str(root / 'readiness.json')}]})
