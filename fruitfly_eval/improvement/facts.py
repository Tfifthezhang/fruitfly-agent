"""Translate structured Agent receipts; never inspect private verifier contents."""
from dataclasses import replace
import json
from pathlib import Path

from fruitfly_agent.core.data_model import LoopDiagnostics
from fruitfly_agent.core.session.observations import read_observation_files, summarize_observations
from fruitfly_agent.improvement.contracts.facts import ArtifactFact, UsageFact
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.execution.facts import attach_facts, loop_fact_values, receipt_facts


def attach_benchmark_facts(record, root, artifacts, *, interrupted=False, trial=None):
    if trial is None:
        from .evidence import trial_directories
        directories = trial_directories(root)
        trial = directories[0] if len(directories) == 1 else None
    sessions = [Path(trial) / 'agent/session.jsonl'] if trial is not None else list(Path(root).glob('artifacts/harbor/*/*/agent/session.jsonl'))
    evidence = list(record.artifacts)
    values = {}
    termination_source = 'unavailable'
    collected = []
    if (len(sessions) == 1 and sessions[0].is_file() and not sessions[0].is_symlink()
            and sessions[0].resolve().is_relative_to(Path(root).resolve())):
        session = sessions[0]
        diagnostics = None
        tool_results = 0
        with session.open(encoding='utf-8', errors='replace' if interrupted else 'strict') as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    if not isinstance(item, dict):
                        raise ValueError('session entry must be an object')
                except ValueError:
                    if interrupted:
                        continue
                    raise
                message = item.get('message')
                if isinstance(message, dict) and message.get('role') == 'toolResult':
                    tool_results += 1
                if item.get('kind') == 'runRecord' and item.get('event') == 'end':
                    raw = item.get('data', {}).get('diagnostics')
                    try:
                        diagnostics = LoopDiagnostics(**raw) if isinstance(raw, dict) else None
                    except (TypeError, ValueError):
                        if not interrupted:
                            raise
                        diagnostics = None
        termination_source = 'native_terminal_diagnostics' if diagnostics is not None else 'missing_terminal_diagnostics'
        values = loop_fact_values(diagnostics)
        if interrupted and diagnostics is None:
            values.update(termination_reason='execution_interrupted', diagnosable=tool_results > 0)
        try:
            paths = [session, *(path for path in sorted(session.with_name(session.name + '.operations').glob('*.jsonl'))
                if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(Path(root).resolve()))]
            observations = summarize_observations(read_observation_files(paths, allow_incomplete=interrupted))
            evidence.append(Resource('agent/0/operations.json', artifacts.put(json.dumps(observations).encode()),
                'application/json', 'diagnostic'))
        except (ValueError, OSError):
            if not interrupted:
                raise
            collected.append(ArtifactFact('operation observations', 'collection_failed', 'Interrupted operation records'))
        agent = session.parent
        for name in ('model-usage.json',):
            path = agent / name
            if path.is_file() and not path.is_symlink():
                if not any(r.path == 'agent/0/' + name for r in evidence):
                    evidence.append(Resource('agent/0/' + name, artifacts.put(path.read_bytes()),
                        'application/json', 'diagnostic'))
                try:
                    from fruitfly_agent.improvement.execution.facts import model_usage_facts
                    requests = json.loads(path.read_bytes())['requests']
                    rows = [event for request in requests for event in (
                        {'kind': 'request', 'id': request['id']},
                        {'kind': 'response', 'attempt_id': request['id'], 'usage': request['usage']})]
                    values['usage'] = (*values.get('usage', ()), *model_usage_facts(rows, record.model_calls))
                except (ValueError, TypeError, KeyError):
                    if not interrupted:
                        raise
        manifest = agent.parent / 'artifacts/manifest.json'
        if manifest.is_file() and not manifest.is_symlink():
            data = manifest.read_bytes()
            evidence.append(Resource('artifact-collection.json', artifacts.put(data), 'application/json', 'diagnostic'))
            try:
                manifest_rows = json.loads(data)
                if not isinstance(manifest_rows, list) or any(not isinstance(item, dict) for item in manifest_rows):
                    raise ValueError('artifact collection manifest must contain object rows')
            except ValueError:
                if not interrupted:
                    raise
                manifest_rows = []
                collected.append(ArtifactFact('artifact collection', 'collection_failed', 'Interrupted collection manifest'))
            for item in manifest_rows:
                status = {'ok': 'collected', 'success': 'collected', 'collected': 'collected', 'empty': 'empty',
                          'failed': 'collection_failed', 'missing': 'absent'}.get(item.get('status'), 'unknown')
                collected.append(ArtifactFact(str(item.get('source') or item.get('destination') or 'unknown'),
                    status, 'Harbor artifact collection manifest'))
    if not values and trial is not None:
        sidecars = [p for p in sorted((Path(trial) / 'agent/session.jsonl.operations').glob('*.jsonl'))
                    if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(Path(root).resolve())]
        if sidecars:
            try:
                observations = summarize_observations(read_observation_files(sidecars, allow_incomplete=interrupted))
                evidence.append(Resource('agent/0/operations.json', artifacts.put(json.dumps(observations).encode()),
                    'application/json', 'diagnostic'))
            except (ValueError, OSError):
                collected.append(ArtifactFact('operation observations', 'collection_failed', 'startup observations unavailable'))
    if not any(v.resource == 'input_tokens' for v in values.get('usage', ())):
        receipt = next((r for r in evidence if r.path.endswith('/model-usage.json')), None)
        if receipt:
            try:
                from fruitfly_agent.improvement.execution.facts import model_usage_facts
                requests = json.loads(artifacts.read(receipt.artifact_id))['requests']
                rows = [event for request in requests for event in (
                    {'kind': 'request', 'id': request['id']},
                    {'kind': 'response', 'attempt_id': request['id'], 'usage': request.get('usage')})]
                values['usage'] = (*values.get('usage', ()), *model_usage_facts(rows, record.model_calls))
            except (ValueError, KeyError, TypeError):
                if not interrupted:
                    raise
    capture = next((r for r in evidence if r.path == 'diagnostics/capture-manifest.json'), None)
    if capture:
        try:
            capture_data = json.loads(artifacts.read(capture.artifact_id))
            if not isinstance(capture_data, dict) or not isinstance(capture_data.get('files'), list):
                raise ValueError('invalid capture receipt')
            capture_rows = capture_data['files']
            for item in capture_rows:
                status = {'collected': 'collected', 'collection_failed': 'collection_failed',
                          'deleted': 'absent'}.get(item.get('status'), 'unknown')
                collected.append(ArtifactFact(str(item.get('path', 'unknown')), status, 'Scoped pre-verifier capture'))
        except (ValueError, KeyError, TypeError):
            collected.append(ArtifactFact('scoped outputs', 'collection_failed', 'Invalid capture receipt'))
    values['usage'] = (*values.get('usage', ()), UsageFact('model_calls', 'execution', record.model_calls,
        'Agent usage receipt; includes main and auxiliary Providers'))
    if collected:
        values['artifacts'] = tuple(collected)
    evidence.append(Resource('diagnostics/termination.json', artifacts.put(json.dumps({
        'termination_reason': values.get('termination_reason', 'unknown'),
        'source': termination_source,
        'scope': 'Missing terminal diagnostics do not establish a timeout or its cause.'}).encode()),
        'application/json', 'diagnostic'))
    # Keep the same granted evidence in the record and facts. No verifier files enter either.
    record = replace(record, artifacts=tuple(evidence))
    facts = receipt_facts(record, artifacts, **values)
    return attach_facts(record, facts, artifacts)
