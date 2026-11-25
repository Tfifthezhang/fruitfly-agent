"""Preserve official grading and produce controller-owned comparison attribution."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_eval.harbor.material import tree_identity, write_json
from fruitfly_eval.improvement.measurement_context import FILENAME
from fruitfly_eval.results import load_harbor_job_result, parse_harbor_job_result


def measurement_plan(receipt: dict[str, Any], runtime: dict[str, Any], *, config_path: Path,
                     models_path: Path, attempts: int, execution: dict[str, Any]) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text())
    profile = config['profiles'][runtime['profile']]
    models = yaml.safe_load(models_path.read_text())
    conditions = content_hash(canonical_json({'models': models, 'execution': execution,
        'runner': receipt['runner'], 'engine': receipt['engine'], 'environment': receipt['runtime']['host'],
        'agent_source': receipt['runtime']['installation']}))
    initial = content_hash(canonical_json({'S': profile.get('S', {}),
        'mounts': receipt['runtime']['mounts'], 'reset': 'fresh official task environment per attempt'}))
    shared = Path(receipt['dataset_material']['root']) / 'shared'
    rows = {}
    for task in receipt['tasks']:
        tests = Path(task['path']) / 'tests'
        scorer = content_hash(canonical_json({'runner': receipt['runner']['source_sha256'],
            'tests': tree_identity(tests) if tests.exists() else None,
            'shared': tree_identity(shared) if shared.exists() else None,
            'verifier': task['configuration'].get('verifier'),
            'steps': task['configuration'].get('steps')}))
        rows[str(Path(task['path']).resolve())] = {'origin_id': receipt['dataset'] + ':' + task['id'],
            'scorer_id': scorer, 'comparison': {'material': content_hash(task['sha256']),
                'conditions': conditions, 'initial_state': initial,
                'source': 'Frozen official WorkBuddy task, engine, verifier and native configuration'}}
    return {'attempts': attempts, 'tasks': rows}


def read_results(path: Path, receipt: dict[str, Any], runtime: dict[str, Any], *,
                 config_path: Path, models_path: Path):
    data = load_harbor_job_result(path, allow_partial=True)
    # The official engine owns reward interpretation. Attribution is written at
    # trial start, before the Agent runs, rather than guessed from directory order.
    from fruitfly_eval.improvement.measurement_context import read
    for trial in path.parent.glob('*/result.json'):
        official = json.loads(trial.read_text())
        context = read(trial.parent, path.parent.parent)
        if context is None:
            raise ValueError('official trial is missing its pre-execution measurement context')
        selected = {t['name']: receipt['dataset'] + ':' + t['id'] for t in receipt['tasks']}
        if official.get('task_name') not in selected:
            raise ValueError('official trial is outside the selected task population')
        if context['origin_id'] != selected[official['task_name']]:
            raise ValueError('official trial and pre-execution task attribution differ')
    return parse_harbor_job_result(data, job_id='workbuddy')
