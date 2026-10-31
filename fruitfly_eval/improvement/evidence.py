"""Collect permitted Agent evidence, keeping official private grading separate."""
from pathlib import Path
import json
from fruitfly_agent.improvement.contracts.tasks import Resource


def collect(root, artifacts, *, interrupted=False):
    root = Path(root)
    resources, calls, known = [], 0, True
    sessions = list(root.glob('artifacts/harbor/*/*/agent/session.jsonl'))
    for index, session in enumerate(sessions):
        if session.is_symlink() or not session.resolve().is_relative_to(root.resolve()):
            known = False
            continue
        agent = session.parent
        for name in ('session.jsonl', 'trajectory.json'):
            path = agent / name
            if path.is_file() and not path.is_symlink():
                resources.append(Resource(f'agent/{index}/{name}', artifacts.put(path.read_bytes()),
                    'application/json', 'trajectory'))
        receipt = agent / 'model-usage.json'
        if not receipt.is_file() or receipt.is_symlink():
            known = False
        else:
            try:
                value = json.loads(receipt.read_text())
                if (value.get('schema_version') != 1 or type(value.get('used')) is not int
                        or value['used'] < 0 or not isinstance(value.get('requests'),list)
                        or len(value['requests']) != value['used']
                        or len({v['id'] for v in value['requests']}) != value['used']):
                    raise ValueError('invalid model-call receipt')
                calls += value['used']
            except (ValueError, TypeError, KeyError, AttributeError, UnicodeDecodeError):
                if not interrupted:
                    raise
                known = False
        # Harbor collects task-declared files. Only successful collected files
        # under this task artifact root are eligible; never expose verifier files.
        collected = agent.parent / 'artifacts'
        if collected.is_dir():
            for path in sorted(collected.rglob('*')):
                if path.is_file() and not path.is_symlink() and path.name != 'manifest.json' and path.resolve().is_relative_to(collected.resolve()) and path.resolve().is_relative_to(root.resolve()):
                    resources.append(Resource(f'deliverables/{index}/' + path.relative_to(collected).as_posix(),
                        artifacts.put(path.read_bytes()), 'application/octet-stream', 'deliverable'))
    return tuple(resources), calls if known and sessions else None
