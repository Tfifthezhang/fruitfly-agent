"""Offline archive projections using the same evidence builder as Improvement."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path

from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial, Resource
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.lab.improvement.evidence.indexing import organize_evidence, DERIVED_PATHS
from fruitfly_agent.lab.improvement.evidence.decoding import decode_rows
from fruitfly_agent.lab.improvement.evidence import decoding, events, indexing
from fruitfly_agent.lab.improvement.evidence import coverage as coverage_module
from .harbor.material import write_json
from .improvement.evidence import collect, trial_directories, answer_evidence
from .improvement.facts import attach_benchmark_facts


def organize_run(run, *, output=None, portable=False):
    root = Path(run).resolve(strict=True)
    if not (root / 'artifacts').is_dir():
        raise ValueError('organize requires an evaluation directory containing artifacts/')
    control = root / 'artifacts/harbor/control.json'
    if control.is_file() and json.loads(control.read_bytes()).get('state') not in {'finished'}:
        raise ValueError('evaluation retirement is unconfirmed; organize only stopped archives')
    raw_target = Path(output).absolute() if output else root / 'evidence'
    if raw_target.is_symlink():
        raise ValueError('evidence output must not be a symlink')
    target = raw_target.resolve()
    if target == root or root.is_relative_to(target) or target.is_relative_to(root / 'artifacts'):
        raise ValueError('evidence output overlaps original archive')
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError('evidence output must not traverse symlinks')
    target.mkdir(parents=True, exist_ok=True)
    manifest = {'schema_version': 1, 'organizer': 'layered-evidence-2', 'trials': [],
                'portable': portable, 'status': 'complete',
                'scope': 'permitted retained evidence; archive identities do not reconstruct missing runtime state'}
    implementation_files = [Path(__file__), Path(__file__).parent / 'trajectory.py',
        Path(__file__).parent / 'improvement/evidence.py', Path(__file__).parent / 'improvement/facts.py',
        *(Path(module.__file__) for module in (decoding, events, coverage_module, indexing))]
    manifest['implementation_files'] = {p.relative_to(Path(__file__).parent.parent).as_posix():
        hashlib.sha256(p.read_bytes()).hexdigest() for p in implementation_files}
    for trial in trial_directories(root):
        key = trial.name + '-' + hashlib.sha256(trial.relative_to(root).as_posix().encode()).hexdigest()[:8]
        destination = target / key
        if destination.is_symlink():
            raise ValueError('trial evidence directory is a symlink')
        destination.mkdir(exist_ok=True)
        artifacts, origins = MemoryArtifacts(), {}
        try:
            resources, calls = collect(root, artifacts, interrupted=True, trial=trial, origins=origins)
            if not any(r.path.endswith('/trajectory.json') for r in resources):
                native = next((r for r in resources if r.path.endswith('/session.jsonl')), None)
                if native:
                    from .trajectory import session_trajectory
                    try:
                        projection = session_trajectory(origins[native.path])
                        projection['extra']['canonical_source'] = native.artifact_id
                        resources = (*resources, Resource('agent/0/trajectory-reprocessed.json',
                            artifacts.put(canonical_json(projection).encode()), 'application/json', 'trajectory'))
                    except (ValueError, TypeError, KeyError, OSError, AttributeError):
                        pass  # Native parse gaps remain visible; no original is replaced.
            instruction = ''
            for resource in resources:
                if resource.path.endswith('/session.jsonl'):
                    rows, _, _ = decode_rows(artifacts.read(resource.artifact_id).decode('utf-8'))
                    for row in rows:
                        message = row.value.get('message', {})
                        if message.get('role') == 'user':
                            content = message.get('content', [])
                            instruction = content if isinstance(content, str) else ''.join(b.get('text', '') for b in content if b.get('type') == 'text')
                            break
            task = TaskMaterial('archive-task', instruction or 'Task instruction unavailable in retained conversation.')
            identity = content_hash(canonical_json([asdict(r) for r in resources]))
            answer = answer_evidence(resources, artifacts)
            resources = (*resources, Resource('diagnostics/final-answer.json',
                artifacts.put(canonical_json(answer).encode()), 'application/json', 'diagnostic'))
            result = trial / 'result.json'
            status = 'cancelled'
            if result.is_file() and not result.is_symlink():
                official = json.loads(result.read_bytes())
                status = 'error' if official.get('exception_info') else 'completed'
            record = ExecutionRecord('archive-' + identity[7:23], task.task_id, task.material_id,
                identity, identity, identity, status, answer['text'][:120000], resources, calls)
            record = attach_benchmark_facts(record, root, artifacts, interrupted=True, trial=trial)
            record = organize_evidence(task, record, artifacts)
            source_rows = []
            for resource in record.artifacts:
                name = 'navigation-sources.json' if resource.path == 'evidence/sources.json' else resource.path.removeprefix('evidence/')
                path = destination / name if resource.path in DERIVED_PATHS else None
                original = origins.get(resource.path)
                if path is not None:
                    if path.is_symlink():
                        raise ValueError('derived evidence path is a symlink')
                    path.write_bytes(artifacts.read(resource.artifact_id))
                elif original is None or portable:
                    path = destination / 'resources' / resource.path
                    # All resource paths already satisfy the common relative-path contract.
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
                        raise ValueError('export resource traverses a symlink')
                    path.write_bytes(artifacts.read(resource.artifact_id))
                else:
                    path = original
                source_rows.append({**asdict(resource), 'location': os.path.relpath(path, target)})
            # The exported source catalog resolves originals and generated resources.
            write_json(destination / 'sources.json', {'sources': source_rows, 'archive_projection': True,
                'identity_scope': 'retained resource bytes, not a reconstructed benchmark harness'})
            coverage = json.loads(artifacts.read(next(r.artifact_id for r in record.artifacts if r.path == 'evidence/coverage.json')))
            manifest['trials'].append({'trial_id': trial.name, 'directory': key, 'run_id': record.run_id,
                'status': 'complete' if coverage['evidence_complete'] else 'partial', 'coverage': coverage['dimensions']})
        except Exception as exc:
            write_json(destination / 'organization-error.json', {'status': 'failed', 'reason': type(exc).__name__, 'detail': str(exc)[:500]})
            manifest['trials'].append({'trial_id': trial.name, 'directory': key, 'status': 'failed', 'reason': type(exc).__name__})
        if manifest['trials'][-1]['status'] != 'complete':
            manifest['status'] = 'partial'
    if not manifest['trials']:
        manifest.update(status='unavailable', reason='No retained Harbor trial evidence')
    preparation = root / 'artifacts/harbor/preparation.json'
    inventory = []
    if preparation.is_file() and not preparation.is_symlink():
        prepared = json.loads(preparation.read_bytes())
        request_path = root / 'request.json'
        request = json.loads(request_path.read_bytes()) if request_path.is_file() else {}
        attempts = request.get('execution', {}).get('attempts', 1)
        manifest['expected_attempts'] = len(prepared.get('tasks', [])) * attempts
        manifest['observed_trials'] = len(manifest['trials'])
        manifest['missing_attempts'] = max(0, manifest['expected_attempts'] - manifest['observed_trials'])
        if manifest['missing_attempts']:
            manifest['status'] = 'partial'
        runtime = prepared.get('runtime', {})
        for label, path in [('runtime-source', runtime.get('source')), *[
                ('task-material', t.get('path')) for t in prepared.get('tasks', [])]]:
            if path:
                location = Path(path)
                inventory.append({'kind': label, 'location': str(location),
                    'availability': 'external-present' if location.exists() else 'external-unavailable',
                    'included_in_evidence_export': False})
    write_json(target / 'material-inventory.json', {'dependencies': inventory,
        'note': 'External runtime/task snapshots and image bytes are not included in a permitted evidence export.'})
    write_json(target / 'manifest.json', manifest)
    return manifest
