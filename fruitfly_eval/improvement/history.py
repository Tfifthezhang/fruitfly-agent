"""Freeze permitted historical Eval evidence as a benchmark-neutral research batch."""
from dataclasses import asdict
import json
from pathlib import Path
from fruitfly_agent.improvement.contracts.research import ResearchBatch
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial, Resource
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_agent.lab.improvement.evidence.indexing import organize_evidence
from .evidence import collect, answer_evidence, trial_directories, safe_path
from .facts import attach_benchmark_facts
from fruitfly_eval.results import trial_outcome


def import_history(run, artifacts, *, task_names=(), related_records=None, evidence_paths=None):
    root = Path(run).resolve(strict=True)
    # Experiment exports place the completed Eval directory under run/.
    nested = root / 'run'
    if not (root / 'artifacts/harbor').is_dir() and (nested / 'artifacts/harbor').is_dir():
        if not safe_path(nested, root):
            raise ValueError('nested Eval evidence must not traverse symlinks')
        root = nested
    configurations = []
    for base in (root, root.parent, *((Path(related_records).resolve(),) if related_records else ())):
        for relative in ('report.json', 'request.json', 'config/default-config.yaml', 'config/models.yaml',
                         'config/eval-tb21-full-c3.json', 'config/eval-host-tb21-full.yaml', 'report/report.json'):
            path = base / relative
            if path.is_file() and safe_path(path, base):
                # Configuration values are evidence, never executable instructions.
                import yaml
                value = json.loads(path.read_text()) if path.suffix == '.json' else yaml.safe_load(path.read_text())
                def scrub(item):
                    if isinstance(item, dict):
                        return {k: '[REDACTED]' if k.lower() in {'api_key', 'password', 'secret', 'authorization'} else scrub(v) for k, v in item.items()}
                    if isinstance(item, list): return [scrub(v) for v in item]
                    return item
                reference = artifacts.put(canonical_json(scrub(value)).encode())
                configurations.append({'path': str(path), 'artifact_id': reference})
    tasks: dict[str, TaskMaterial] = {}
    wanted, records, observations = set(task_names), [], []
    for directory in trial_directories(root):
        result = directory / 'result.json'
        official = json.loads(result.read_bytes()) if result.is_file() and safe_path(result, root) else {}
        name = official.get('task_name', directory.name)
        if wanted and name not in wanted:
            continue
        resources, calls = collect(root, artifacts, interrupted=True, trial=directory, evidence_paths={k: v for k, v in (evidence_paths or {}).items()
            if k.startswith(directory.relative_to(root).as_posix() + "/")})
        material = next(r for r in resources if r.path == 'diagnostics/task.json')
        task_data = json.loads(artifacts.read(material.artifact_id))
        instruction, present = task_data['instruction'], task_data['instruction_available']
        key = 'archive-' + content_hash(name)[7:31]
        task = TaskMaterial(key, instruction or 'Task instruction unavailable in retained evidence.',
            origin=name, environment_id='retained-eval-evidence')
        if key in tasks and tasks[key] != task:
            raise ValueError('historical task instructions differ across attempts: ' + name)
        tasks[key] = task
        identity = content_hash(canonical_json({'trial': official.get('id', directory.name),
            'resources': [asdict(r) for r in resources]}))
        answer = answer_evidence(resources, artifacts)
        resources = tuple(r for r in resources if r.path != 'diagnostics/answer-material.json')
        provenance = {'task_name': name, 'instruction_available': present, 'archive_identity': identity,
            'scope': 'Retained bytes; old harness, source and learning state are not reconstructed.',
            'configuration_sources': configurations,
            'unknown': ['original harness reconstruction', 'initial learning state'],
            'exception_type': (official.get('exception_info') or {}).get('exception_type')}
        resources = (*resources, Resource('diagnostics/history.json', artifacts.put(canonical_json(provenance).encode()),
            'application/json', 'diagnostic'), Resource('diagnostics/final-answer.json',
            artifacts.put(canonical_json(answer).encode()), 'application/json', 'diagnostic'))
        receipt = ExecutionRecord('history-' + identity[7:31], key, task.material_id, identity, identity, identity,
            'error' if official.get('exception_info') else 'completed' if official else 'cancelled',
            answer['text'][:120000], resources, calls)
        receipt = attach_benchmark_facts(receipt, root, artifacts, interrupted=True, trial=directory)
        records.append(organize_evidence(task, receipt, artifacts))
        outcome = trial_outcome(official)
        observations.append({'run_id': receipt.run_id, 'name': 'official_reward',
            'official_status': outcome['status'], 'eligible': outcome['eligible'],
            'exception_type': outcome['error']['type'] if outcome['error'] else None,
            'agent_elapsed_seconds': outcome['agent_elapsed_seconds'],
            'interpretation': 'Shared Eval result rules; raw reward is not an execution-success certificate.',
            'value': (official.get('verifier_result') or {}).get('rewards'),
            'source': str(result), 'source_identity': content_hash(result.read_bytes().decode())
                if result.is_file() and safe_path(result, root) else None})
    if evidence_paths:
        retained = {r.path.removeprefix('originals/') for record in records for r in record.artifacts if r.path.startswith('originals/')}
        if set(evidence_paths) - retained:
            raise ValueError('supplement paths are outside selected task evidence')
    if not tasks or wanted - {t.origin for t in tasks.values()}:
        raise ValueError('requested historical task records are unavailable')
    observations.append({'name': 'historical_configuration', 'sources': configurations,
        'scope': 'Retained declarations and receipts; unknown state is not inferred.'})
    return ResearchBatch(tuple(tasks.values()), tuple(records), tuple(observations))
