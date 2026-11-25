"""Operations imported only in the independent official WorkBuddy Python environment."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
from typing import Any

from fruitfly_eval.harbor.host import HostConfig
from fruitfly_eval.harbor.material import write_json
from .configuration import RUNNER_HARBOR_VERSION


def describe(checkout: Path) -> dict[str, Any]:
    import workbuddy_bench  # type: ignore[import-not-found, import-untyped, unused-ignore]
    import harbor  # type: ignore[import-not-found, import-untyped, unused-ignore]
    if importlib.metadata.version('harbor') != RUNNER_HARBOR_VERSION:
        raise ValueError('isolated runner must install Harbor ' + RUNNER_HARBOR_VERSION)
    if not Path(workbuddy_bench.__file__).resolve().is_relative_to((checkout / 'src').resolve()):
        raise ValueError('WorkBuddy imports must resolve from the pinned checkout')
    from harbor.job import Job  # type: ignore[import-not-found, import-untyped, unused-ignore]
    from harbor.agents.installed.base import BaseInstalledAgent  # type: ignore[import-not-found, import-untyped, unused-ignore]
    from fruitfly_eval.workbuddy.agent import WorkBuddyFruitFlyAgent
    if not issubclass(WorkBuddyFruitFlyAgent, BaseInstalledAgent) or WorkBuddyFruitFlyAgent.__abstractmethods__:
        raise ValueError('native Agent bridge is incompatible with the isolated engine')
    if not all(callable(getattr(Job, name, None)) for name in (
            'on_agent_started', 'on_agent_ended', 'on_trial_started', 'on_trial_ended', 'on_trial_cancelled')):
        raise ValueError('isolated engine lacks required public lifecycle hooks')
    from fruitfly_eval.harbor.controller import environment_snapshot
    from fruitfly_eval.harbor.material import tree_identity
    return {'controller': environment_snapshot(), 'python': sys.executable,
            'engine': {'harbor': RUNNER_HARBOR_VERSION,
                       'sha256': tree_identity(Path(harbor.__file__).parent, exclude_bytecode=True)}}


def dispatch(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    checkout = Path(payload['checkout'])
    state = describe(checkout)
    if operation == 'describe':
        return state
    if operation == 'validate_job':
        from harbor.models.job.config import JobConfig  # type: ignore[import-not-found, import-untyped, unused-ignore]
        JobConfig.model_validate(payload['job'])
        return {'valid': True}
    if operation == 'bench':
        from workbuddy_bench.runner.bench_config import load_bench  # type: ignore[import-not-found, import-untyped, unused-ignore]
        return {'bench': load_bench(checkout / 'configs', payload['dataset'], repo_root=checkout)}
    if operation == 'resources':
        from fruitfly_eval.harbor.selection import task_requirements
        import tomllib
        rows = {}
        for filename in payload['tasks']:
            path = Path(filename)
            config = tomllib.loads((path / 'task.toml').read_text())
            rows[str(path.resolve())] = task_requirements({'id': path.name, 'path': str(path), 'configuration': config})
        return {'resources': rows}
    if operation == 'normalize':
        from workbuddy_bench.runner.prepare_tasks import ensure_composite_verifier_contract, ensure_task_user  # type: ignore[import-not-found, import-untyped, unused-ignore]
        tasks = Path(payload['dataset']) / 'tasks'
        contract = ensure_composite_verifier_contract(tasks)
        users = ensure_task_user(tasks, agent_user=payload['agent_user'], verifier_user=payload['verifier_user'])
        return {'contract_changes': contract, 'user_changes': users}
    if operation == 'probe':
        from fruitfly_eval.harbor.environments import probe_environment
        host = HostConfig.read(Path(payload['workspace']), payload['host'])
        async def prepare_user(environment, definition):
            from types import SimpleNamespace
            from workbuddy_bench.agents._agent_user import ensure_agent_user  # type: ignore[import-not-found, import-untyped, unused-ignore]
            class Commands:
                async def exec_as_root(self, target, *, command):
                    return await environment.exec(command=command, user='root', timeout_sec=60)
            await ensure_agent_user(Commands(), SimpleNamespace(default_user=definition['user']))
        return probe_environment(payload['task'], payload['runtime'], payload['docker'],
            Path(payload['directory']), host=host,
            environment_import='fruitfly_eval.workbuddy.environment:PreparedWorkBuddyEnvironment',
            before_probe=prepare_user)
    raise ValueError('unsupported isolated engine operation: ' + operation)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--response', type=Path, required=True)
    args = parser.parse_args()
    try:
        request = json.loads(args.request.read_text())
        value = {'ok': True, 'result': dispatch(request['operation'], request['payload'])}
        code = 0
    except Exception as exc:
        value = {'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)}
        code = 1
    write_json(args.response, value)
    raise SystemExit(code)


if __name__ == '__main__':
    main()
