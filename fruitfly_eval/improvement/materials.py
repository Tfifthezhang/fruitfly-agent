"""Freeze compact task materials; retain hash-checked locators for explicit deep reads."""
import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any

from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.lab.improvement.evidence.decoding import decode_rows


def _identity(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return 'sha256:' + digest.hexdigest()


def collect_materials(root, artifacts, *, interrupted=False, trial=None, origins=None, evidence_paths=None):
    from .evidence import safe_path, trial_directories
    root = Path(root).resolve()
    from fruitfly_agent.improvement.contracts.validation import relative_path
    from fruitfly_agent.improvement.contracts.versions import require_hash
    requested = dict(evidence_paths or {})
    for path, identity in requested.items():
        relative_path(path)
        require_hash(identity)
    matched = set()
    resources, total_calls, known = [], 0, True
    trials = (Path(trial),) if trial is not None else trial_directories(root)
    for index, directory in enumerate(trials):
        if not safe_path(directory, root) or not safe_path(directory / 'agent', root):
            raise ValueError('trial evidence escapes evaluation root')
        agent = directory / 'agent'
        locators = []
        def locate(path, logical, kind='diagnostic', expected=None):
            if not path.is_file() or not safe_path(path, root):
                return None
            identity = _identity(path)
            relative = path.relative_to(root).as_posix()
            entry = {'path': relative, 'logical_path': logical, 'artifact_id': identity,
                     'bytes': path.stat().st_size, 'kind': kind, 'status': 'external',
                     'media_type': mimetypes.guess_type(path.name)[0] or 'application/octet-stream'}
            if expected and identity != 'sha256:' + expected.removeprefix('sha256:'):
                entry['status'] = 'invalid'
            locators.append(entry)
            if relative in requested:
                if requested[relative] != identity or entry['status'] == 'invalid':
                    raise ValueError('supplement evidence hash mismatch: ' + relative)
                data = path.read_bytes()
                if 'sha256:' + hashlib.sha256(data).hexdigest() != identity:
                    raise ValueError('supplement evidence changed during collection')
                resources.append(Resource('originals/' + relative, artifacts.put(data), entry['media_type'],
                                          'diagnostic' if kind == 'trajectory' else kind))
                entry['status'] = 'retained'
                matched.add(relative)
            return entry
        def retain(path, logical):
            entry = locate(path, logical)
            if entry is not None:
                data = path.read_bytes()
                if 'sha256:' + hashlib.sha256(data).hexdigest() != entry['artifact_id']:
                    raise ValueError('evidence changed during collection')
                resources.append(Resource(logical, artifacts.put(data), entry['media_type'], 'diagnostic'))
                entry['status'] = 'retained'
                if origins is not None:
                    origins[logical] = path
        prefix = f'agent/{index}/'
        native = agent / 'session.jsonl'
        source = native if native.is_file() and safe_path(native, root) else agent / 'trajectory.json'
        instruction = ''
        answer: dict[str, Any] = {'state': 'absent', 'text': '', 'source': None}
        gaps, projected = [], []
        if source.is_file() and safe_path(source, root):
            locator = locate(source, prefix + source.name, 'trajectory')
            data = source.read_bytes()
            if 'sha256:' + hashlib.sha256(data).hexdigest() != locator['artifact_id']:
                raise ValueError('trajectory changed during collection')
            rows, source_format, gaps = decode_rows(data.decode('utf-8', errors='replace'))
            try:
                data.decode('utf-8')
            except UnicodeDecodeError:
                gaps.append({'reason': 'invalid UTF-8; projection contains replacement characters'})
            for row in rows:
                raw = row.value
                message = raw.get('message')
                if not isinstance(message, dict):
                    if source_format != 'atif':
                        continue
                    role = {'agent': 'assistant', 'user': 'user', 'system': 'custom'}.get(raw.get('source'), 'custom')
                    message = {'role': role, 'content': raw.get('message', '')}
                role = str(message.get('role', ''))
                if role not in {'user', 'assistant', 'toolResult', 'custom'}:
                    continue
                origin = {'path': locator['path'], 'artifact_id': locator['artifact_id'],
                          'start': row.start, 'end': row.end}
                content = message.get('content', [])
                text = content if isinstance(content, str) else ''.join(
                    b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text')
                if role == 'user' and not instruction:
                    instruction = text
                calls = [b for b in content if isinstance(b, dict) and b.get('type') == 'toolCall'] if isinstance(content, list) else []
                if source_format == 'atif':
                    calls = [{'type': 'toolCall', 'id': c.get('tool_call_id'), 'name': c.get('function_name'),
                              'input': c.get('arguments')} for c in raw.get('tool_calls', [])]
                if role == 'assistant':
                    answer = {'state': 'final' if text and message.get('stopReason') == 'stop' and not calls and not gaps else 'partial',
                              'text': text, 'source': origin}
                blocks: list[dict[str, Any]] = [{'type': 'text', 'text': text[:2000]}] if text else []
                for call in calls:
                    arguments = canonical_json(call.get('input'))
                    blocks.append({'type': 'toolCall', 'id': call.get('id'), 'name': call.get('name'),
                                   'input': arguments[:2000], 'input_characters': len(arguments),
                                   'input_truncated': len(arguments) > 2000})
                clean = {k: message[k] for k in ('role', 'toolCallId', 'toolName', 'isError', 'stopReason') if k in message}
                clean['content'] = blocks
                projected.append({'type': 'message', 'timestamp': raw.get('timestamp'), 'message': clean,
                                  'source': origin, 'text_characters': len(text), 'text_truncated': len(text) > 2000})
                if source_format == 'atif':
                    for result in raw.get('observation', {}).get('results', []):
                        output = result.get('content', '')
                        output = output if isinstance(output, str) else canonical_json(output)
                        projected.append({'type': 'message', 'source': origin, 'text_characters': len(output),
                            'text_truncated': len(output) > 2000, 'message': {'role': 'toolResult',
                            'toolCallId': result.get('source_call_id'), 'isError': result.get('extra', {}).get('is_error'),
                            'content': [{'type': 'text', 'text': output[:2000]}]}})
            resources.append(Resource(prefix + 'reading-trajectory.jsonl', artifacts.put(
                ('\n'.join(canonical_json(v) for v in projected)).encode()), 'application/jsonl', 'trajectory'))
        else:
            gaps.append({'reason': 'native Session and converted trajectory unavailable'})
        for name in ('model-usage.json', 'process.json', 'trajectory-status.json'):
            retain(agent / name, prefix + name)
        usage = agent / 'model-usage.json'
        try:
            value = json.loads(usage.read_bytes()) if safe_path(usage, root) else {}
            if (value.get('schema_version') != 1 or type(value.get('used')) is not int or value['used'] < 0
                    or len(value['requests']) != value['used'] or len({v['id'] for v in value['requests']}) != value['used']):
                raise ValueError('invalid model-call receipt')
            total_calls += value['used']
        except (OSError, ValueError, KeyError, TypeError):
            if not interrupted and usage.is_file():
                raise
            known = False
        captured = agent / 'evidence-capture'
        retain(captured / 'manifest.json', 'diagnostics/capture-manifest.json')
        retain(captured / 'baseline.json', 'diagnostics/capture-baseline.json')
        manifest = captured / 'manifest.json'
        if manifest.is_file() and safe_path(manifest, root):
            try:
                capture = json.loads(manifest.read_bytes())
                for entry in capture['files']:
                    if entry.get('status') != 'collected':
                        continue
                    relative = Path(entry['archive_path'])
                    if relative.is_absolute() or '..' in relative.parts:
                        raise ValueError('unsafe capture entry')
                    kind = 'diagnostic' if relative.parts[0] == 'tool-output' else 'deliverable'
                    locate(captured / relative, 'captured/' + relative.as_posix(), kind, entry['sha256'])
            except (OSError, ValueError, KeyError, TypeError):
                if not interrupted:
                    raise
                gaps.append({'reason': 'capture manifest unavailable or invalid'})
        collected = directory / 'artifacts'
        retain(collected / 'manifest.json', prefix + 'artifact-collection.json')
        if collected.is_dir() and safe_path(collected, root):
            for path in sorted(collected.rglob('*')):
                if path.name != 'manifest.json':
                    locate(path, 'deliverables/' + path.relative_to(collected).as_posix(), 'deliverable')
        for name, value in (('task', {'instruction': instruction, 'instruction_available': bool(instruction)}),
                            ('answer-material', answer), ('reading-scope', {'gaps': gaps,
                             'scope': 'Compact projection; original bytes are external unless explicitly supplemented.',
                             'archive_root': str(root), 'sources': locators})):
            resources.append(Resource('diagnostics/' + name + '.json', artifacts.put(canonical_json(value).encode()),
                                      'application/json', 'diagnostic'))
    if requested.keys() - matched:
        raise ValueError('supplement paths are unavailable or outside permitted evidence: ' + ', '.join(sorted(requested.keys() - matched)))
    return tuple(resources), total_calls if known and trials else None
