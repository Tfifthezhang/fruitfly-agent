"""Collect permitted Agent evidence, keeping official private grading separate."""
from pathlib import Path
import json
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


def collect(root, artifacts, *, interrupted=False, trial=None, origins=None, evidence_paths=None):
    from .materials import collect_materials
    return collect_materials(root, artifacts, interrupted=interrupted, trial=trial,
                             origins=origins, evidence_paths=evidence_paths)


def answer_evidence(resources, artifacts):
    """Reference the last committed assistant response without inventing a final."""
    retained = next((r for r in resources if r.path in {'diagnostics/final-answer.json', 'diagnostics/answer-material.json'}), None)
    if retained is not None:
        return json.loads(artifacts.read(retained.artifact_id))
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
