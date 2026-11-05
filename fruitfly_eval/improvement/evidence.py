"""Collect permitted Agent evidence, keeping official private grading separate."""
from pathlib import Path
import json
import mimetypes
from typing import Any
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.lab.improvement.evidence.decoding import decode_rows


def safe_path(path, root):
    return (not path.is_symlink() and path.resolve().is_relative_to(root)
            and not any(p.is_symlink() for p in path.parents if p.is_relative_to(root)))


def trial_directories(root):
    root = Path(root).resolve()
    return tuple(path for path in sorted(root.glob('artifacts/harbor/*/*'))
                 if path.is_dir() and safe_path(path, root)
                 and ((path / 'agent').is_dir() or (path / 'result.json').is_file()))


def collect(root, artifacts, *, interrupted=False, trial=None, origins=None):
    root = Path(root).resolve()
    trials = (Path(trial),) if trial is not None else trial_directories(root)
    resources, calls, known = [], 0, True
    for index, directory in enumerate(trials):
        if directory.is_symlink() or not directory.resolve().is_relative_to(root):
            raise ValueError('trial evidence escapes evaluation root')
        agent = directory / 'agent'
        if agent.is_symlink():
            raise ValueError('Agent evidence directory must not be a symlink')
        def add(path, logical, kind='diagnostic'):
            if path.is_file() and safe_path(path, root):
                media = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
                resources.append(Resource(logical, artifacts.put(path.read_bytes()), media, kind))
                if origins is not None:
                    origins[logical] = path
        for name in ('session.jsonl', 'trajectory.json', 'events.jsonl'):
            add(agent / name, f'agent/{index}/{name}', 'trajectory')
        if not (agent / 'events.jsonl').is_file():
            add(agent / 'live-events.jsonl', f'agent/{index}/live-events.jsonl', 'trajectory')
        for name in ('trajectory-status.json', 'model-usage.json', 'process.json'):
            add(agent / name, f'agent/{index}/{name}')
        for path in sorted((agent / 'session.jsonl.operations').glob('*.jsonl')):
            add(path, f'agent/{index}/operations-originals/{path.name}', 'trajectory')
        receipt = agent / 'model-usage.json'
        if not receipt.is_file() or not safe_path(receipt, root):
            known = False
        else:
            try:
                value = json.loads(receipt.read_text())
                if (value.get('schema_version') != 1 or type(value.get('used')) is not int
                        or value['used'] < 0 or not isinstance(value.get('requests'), list)
                        or len(value['requests']) != value['used']
                        or len({v['id'] for v in value['requests']}) != value['used']):
                    raise ValueError('invalid model-call receipt')
                calls += value['used']
            except (ValueError, TypeError, KeyError, AttributeError, UnicodeDecodeError):
                if not interrupted:
                    raise
                known = False
        captured = agent / 'evidence-capture'
        manifest = captured / 'manifest.json'
        add(manifest, 'diagnostics/capture-manifest.json')
        add(captured / 'baseline.json', 'diagnostics/capture-baseline.json')
        if manifest.is_file() and safe_path(manifest, root):
            try:
                capture = json.loads(manifest.read_bytes())
                if not isinstance(capture, dict) or not isinstance(capture.get('files'), list):
                    raise ValueError('invalid capture manifest')
                for entry in capture.get('files', []):
                    if entry.get('status') != 'collected':
                        continue
                    relative = Path(entry['archive_path'])
                    path = captured / relative
                    if relative.is_absolute() or '..' in relative.parts or path.is_symlink() or not path.resolve().is_relative_to(captured.resolve()):
                        raise ValueError('unsafe capture entry')
                    data = path.read_bytes()
                    from hashlib import sha256
                    if sha256(data).hexdigest() != entry['sha256']:
                        raise ValueError('capture content hash mismatch')
                    kind = 'diagnostic' if relative.parts[0] == 'tool-output' else 'deliverable'
                    add(path, f'deliverables/{index}/' + relative.as_posix() if kind == 'deliverable'
                        else 'diagnostics/' + relative.as_posix(), kind)
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                if not interrupted:
                    raise
        collected = directory / 'artifacts'
        if collected.is_dir() and not collected.is_symlink():
            add(collected / 'manifest.json', f'agent/{index}/artifact-collection.json')
            for path in sorted(collected.rglob('*')):
                if path.name != 'manifest.json' and path.resolve().is_relative_to(collected.resolve()):
                    add(path, f'deliverables/{index}/harbor/' + path.relative_to(collected).as_posix(), 'deliverable')
    return tuple(resources), calls if known and trials else None


def answer_evidence(resources, artifacts):
    """Reference the last committed assistant response without inventing a final."""
    answer: dict[str, Any] = {'state': 'absent', 'text': '', 'source': None}
    for resource in resources:
        if not resource.path.endswith('/session.jsonl'):
            continue
        rows, _, gaps = decode_rows(artifacts.read(resource.artifact_id).decode('utf-8'))
        for row in rows:
            message = row.value.get('message', {})
            if message.get('role') != 'assistant':
                continue
            content = message.get('content', [])
            text = content if isinstance(content, str) else ''.join(
                b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text')
            if not text:
                continue
            calls = any(b.get('type') == 'toolCall' for b in content if isinstance(b, dict)) if isinstance(content, list) else False
            answer = {'state': 'final' if message.get('stopReason') == 'stop' and not calls and not gaps else 'partial',
                      'text': text, 'source': {'path': resource.path, 'artifact_id': resource.artifact_id,
                                             'start': row.start, 'end': row.end}}
    return answer
