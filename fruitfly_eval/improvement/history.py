"""Freeze permitted historical Eval evidence as a benchmark-neutral research batch."""
from dataclasses import asdict, replace
import json
from pathlib import Path
from fruitfly_agent.improvement.contracts.research import ResearchBatch
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial, Resource
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_agent.lab.improvement.evidence.indexing import organize_evidence
from .evidence import collect, answer_evidence, trial_directories, safe_path
from .facts import attach_benchmark_facts
from fruitfly_eval.results import trial_outcome, public_trial_outcome


def import_history(run, artifacts, *, task_names=(), related_records=None, evidence_paths=None):
    from fruitfly_agent.improvement.contracts.observations import BatchManifest, PlannedAttempt
    from .observations import official_observation
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
                         'config/config.yaml', 'config/host.yaml', 'report/report.json'):
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
    planned: list[PlannedAttempt] = []
    attempts: dict[str, int] = {}
    attributed = True
    seen_attempts = set()
    origins = {}
    # A retained report can supply canonical benchmark names, without exposing
    # verifier answers. Missing metadata remains a distinct retained namespace.
    report_path = root / 'report.json'
    report = json.loads(report_path.read_text()) if report_path.is_file() and safe_path(report_path, root) else {}
    dataset = report.get('benchmark', {}).get('dataset')
    canonical_names = {}
    for path in sorted((root / 'trials').glob('*.json')):
        if safe_path(path, root):
            row = json.loads(path.read_text())
            canonical_names[row.get('trial_id')] = row.get('task_id')
    # Preserve unstarted attempts when the archive retains its selected
    # preparation and request. Neither task instructions nor verifier files
    # are recovered from the live checkout.
    preparation_path = root / 'artifacts/harbor/preparation.json'
    request_path = root / 'request.json'
    declared_tasks = {}
    declared_attempts = None
    if all(p.is_file() and safe_path(p, root) for p in (preparation_path, request_path)):
        preparation = json.loads(preparation_path.read_text())
        request = json.loads(request_path.read_text())
        count = request.get('execution', {}).get('attempts')
        if type(count) is not int or count < 1:
            raise ValueError('retained execution attempts must be positive')
        declared_attempts = count
        for row in preparation['tasks']:
            name = row['name']
            if wanted and name not in wanted:
                continue
            if name in declared_tasks:
                raise ValueError('duplicate retained prepared task name')
            declared_tasks[name] = row['id']
            key = 'archive-' + content_hash(name)[7:31]
            tasks[key] = TaskMaterial(key, 'Task instruction unavailable in retained evidence.',
                origin=name, environment_id='retained-eval-evidence')
            origins[key] = dataset + ':' + row['id'] if dataset else 'retained:' + content_hash(name)
            planned.extend(PlannedAttempt(key, a) for a in range(count))
    for directory in trial_directories(root):
        from .measurement_context import read as read_context
        context = read_context(directory, root)
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
        if key in attempts and tasks[key] != task:
            raise ValueError('historical task instructions differ across attempts: ' + name)
        tasks[key] = task
        position = attempts.get(key, 0)
        attempt = context['attempt'] if context is not None else position
        attributed = attributed and context is not None
        attempts[key] = position + 1
        if (key, attempt) in seen_attempts:
            raise ValueError('duplicate retained task attempt identity')
        seen_attempts.add((key, attempt))
        if declared_attempts is None:
            planned.append(PlannedAttempt(key, attempt))
        elif name not in declared_tasks or attempt >= declared_attempts:
            raise ValueError('retained trial is outside its declared execution plan')
        canonical_name = canonical_names.get(official.get('id'))
        if key not in origins:
            origins[key] = dataset + ':' + canonical_name if dataset and canonical_name else 'retained:' + content_hash(name)
        if context is not None:
            if dataset and name in declared_tasks and context['origin_id'] != dataset + ':' + declared_tasks[name]:
                raise ValueError('measurement origin differs from its selected preparation')
            origins[key] = context['origin_id']
        identity = content_hash(canonical_json({'trial': official.get('id', directory.name),
            'resources': [asdict(r) for r in resources]}))
        answer = answer_evidence(resources, artifacts)
        resources = tuple(r for r in resources if r.path != 'diagnostics/answer-material.json')
        provenance = {'task_name': name, 'instruction_available': present, 'archive_identity': identity,
            'scope': 'Retained bytes; old harness, source and learning state are not reconstructed.',
            'configuration_sources': configurations,
            'unknown': ['original harness reconstruction', 'initial learning state'],
            'exception_type': (official.get('exception_info') or {}).get('exception_type')}
        resources = (*resources, *(Resource('diagnostics/configuration/' + str(i) + '.json', entry['artifact_id'],
            'application/json', 'diagnostic') for i, entry in enumerate(configurations)
            if Path(entry['path']).suffix in {'.yaml', '.yml'} or Path(entry['path']).name == 'request.json'),
            Resource('diagnostics/history.json', artifacts.put(canonical_json(provenance).encode()),
            'application/json', 'diagnostic'), Resource('diagnostics/final-answer.json',
            artifacts.put(canonical_json(answer).encode()), 'application/json', 'diagnostic'))
        receipt = ExecutionRecord('history-' + identity[7:31], key, task.material_id, identity, identity, identity,
            'error' if official.get('exception_info') else 'completed' if official else 'cancelled',
            answer['text'][:120000], resources, calls)
        receipt = attach_benchmark_facts(receipt, root, artifacts, interrupted=True, trial=directory)
        outcome = trial_outcome(official)
        public_result = {**public_trial_outcome(official),
            'source_identity': content_hash(result.read_text()) if official else None,
            'scope': 'Public outcome projection; verifier source and private answers excluded.'}
        receipt = replace(receipt, artifacts=(*receipt.artifacts,
            Resource('diagnostics/outcome.json', artifacts.put(canonical_json(public_result).encode()),
                'application/json', 'diagnostic')))
        records.append(organize_evidence(task, receipt, artifacts))
        observations.append(official_observation(receipt, official,
            source_identity=public_result['source_identity'], attempt=attempt, context=context))
    if evidence_paths:
        retained = {r.path.removeprefix('originals/') for record in records for r in record.artifacts if r.path.startswith('originals/')}
        if set(evidence_paths) - retained:
            raise ValueError('supplement paths are outside selected task evidence')
    if not tasks or wanted - {t.origin for t in tasks.values()}:
        raise ValueError('requested historical task records are unavailable')
    observations.append({'name': 'historical_configuration', 'sources': configurations,
        'scope': 'Retained declarations and receipts; unknown state is not inferred.'})
    declared = declared_attempts is not None and attributed
    observations.append(BatchManifest(tuple(planned), origins=tuple(origins.items()),
        selection_reason=('Retained selected preparation and controller-attributed original attempts.' if declared else
            'Retained selected preparation and requested attempt count; observed attempts use archive order.'
            if declared_attempts is not None else
            'Retained trials; attempt numbering is archive order, not a reconstructed original plan.'),
        scope_kind='declared' if declared else 'retained-planned' if declared_attempts is not None else 'retained-observed').to_dict())
    return ResearchBatch(tuple(tasks.values()), tuple(records), tuple(observations))
