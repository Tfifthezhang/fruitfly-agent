"""Bounded read-only inventory and file capture inside a prepared task runtime."""
from __future__ import annotations
import argparse
import fnmatch
import hashlib
import json
import os
import re
from pathlib import Path
import stat
import time
import tempfile
from typing import Any

DEFAULTS: dict[str, Any] = {'roots': ['.'], 'extra_paths': [],
            'exclude': ['.fruitfly', '.git', '.env', 'secrets.env', '__pycache__', '.ssh'],
            'max_file_bytes': 268435456, 'max_total_bytes': 1073741824,
            'max_entries': 10000, 'baseline_seconds': 30, 'capture_seconds': 60,
            'include_tool_outputs': True}


def capture_policy(value=None) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError('invalid evidence capture fields')
    result: dict[str, Any] = {key: list(val) if isinstance(val, list) else val for key, val in DEFAULTS.items()}
    result.update(value)
    for name in ('roots', 'extra_paths', 'exclude'):
        entries = result[name]
        if not isinstance(entries, list) or any(not isinstance(p, str) or not p or any(ord(c) < 32 for c in p) for p in entries):
            raise ValueError('evidence paths/exclusions require string lists')
        if len(set(entries)) != len(entries):
            raise ValueError('evidence paths must be distinct')
    if not result['roots']:
        raise ValueError('evidence.roots must not be empty')
    if any(Path(p).is_absolute() or '..' in Path(p).parts for p in result['roots']):
        raise ValueError('evidence.roots must be relative to task working directory without ..')
    if any('..' in Path(p).parts for p in result['extra_paths']):
        raise ValueError('evidence.extra_paths must not contain ..')
    if type(result['include_tool_outputs']) is not bool:
        raise ValueError('evidence.include_tool_outputs must be boolean')
    for name in ('max_file_bytes', 'max_total_bytes', 'max_entries', 'baseline_seconds', 'capture_seconds'):
        if type(result[name]) is not int or result[name] <= 0:
            raise ValueError('evidence limits must be positive integers')
    return result


def open_file(path):
    """Reject symlinks in every path component, including concurrent swaps."""
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        return os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)


def capture(workspace, destination, policy=None, *, phase='final', stage=1, forbidden=()):
    policy = capture_policy(policy)
    workspace, destination = Path(workspace).resolve(), Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    limit = policy['baseline_seconds' if phase == 'baseline' else 'capture_seconds']
    deadline = started + limit
    blocked = [Path(p).resolve() for p in ('/proc', '/sys', '/dev', '/logs', '/tests', '/installed-agent', '/opt/fruitfly-eval-dependencies', *forbidden)]
    blocked.append(destination)
    previous = {}
    baseline_path = destination / f'baseline-{stage}.json'
    if phase == 'final' and baseline_path.is_file():
        baseline = json.loads(baseline_path.read_bytes())
        previous = {r['path']: r for r in baseline['files'] if r.get('sha256')}
    else:
        baseline = {'status': 'unknown'}
    rows: list[dict[str, Any]] = []
    seen: set[Path] = set()
    total = 0
    complete = True
    explicit_paths = [Path(os.path.abspath(p if Path(p).is_absolute() else workspace / p)) for p in policy['extra_paths']]
    roots = [(p, False, 'files') for p in policy['roots']] + [(p, True, 'files') for p in policy['extra_paths']]
    if phase == 'final' and policy['include_tool_outputs']:
        session = destination.parent / 'session.jsonl'
        if session.is_file() and session.stat().st_size <= policy['max_total_bytes']:
            with session.open(encoding='utf-8') as stream:
                for line in stream:
                    if time.monotonic() >= deadline:
                        complete = False
                        break
                    try:
                        message = json.loads(line).get('message', {})
                        paths = [message.get('details', {}).get('full_output_path')]
                        content = message.get('content', [])
                        texts = [content] if isinstance(content, str) else [b.get('text', '') for b in content if isinstance(b, dict)]
                        paths.extend(p for text in texts for p in re.findall(r'Full output:\s*([^\]\s]+)', text))
                        for log_path in dict.fromkeys(p for p in paths if isinstance(p, str)):
                            if message.get('role') != 'toolResult':
                                continue
                            candidate = Path(log_path)
                            if candidate.parent == Path(tempfile.gettempdir()) and candidate.name.startswith('fruitfly-bash-'):
                                roots.append((log_path, True, 'tool-output'))
                            else:
                                rows.append({'path': log_path, 'status': 'skipped', 'reason': 'unrecognized tool-output scope'})
                                complete = False
                    except (ValueError, TypeError, AttributeError):
                        complete = False
    for root_index, (configured, explicit, category) in enumerate(roots):
        root = Path(configured)
        root = root if root.is_absolute() else workspace / root
        # Keep symlink identity: resolving it first would follow a scope escape.
        root = Path(os.path.abspath(root))
        if root.resolve() != root:
            rows.append({'path': str(root), 'status': 'excluded', 'reason': 'symlink in root path'})
            complete = False
            continue
        if root == Path('/') or any(root == p or root.is_relative_to(p) for p in blocked):
            rows.append({'path': str(root), 'status': 'excluded', 'reason': 'protected root'})
            complete = False
            continue
        pending = [root]
        while pending:
            path = pending.pop()
            if time.monotonic() >= deadline or len(seen) >= policy['max_entries']:
                rows.append({'path': str(path), 'status': 'skipped', 'reason': 'time or entry limit'})
                complete = False
                pending.clear()
                break
            if path in seen:
                continue
            seen.add(path)
            relative = path.relative_to(root) if path != root else Path(path.name)
            if any(path == p or path.is_relative_to(p) for p in blocked) or any(
                    fnmatch.fnmatch(part, pattern) for part in path.parts for pattern in policy['exclude']):
                continue
            row: dict[str, Any] = {'path': str(path), 'status': 'inventoried', 'stage': stage}
            try:
                before = path.lstat()
                if stat.S_ISLNK(before.st_mode):
                    rows.append({**row, 'status': 'excluded', 'reason': 'symlink', 'target': os.readlink(path)})
                    continue
                if stat.S_ISDIR(before.st_mode):
                    pending.extend(sorted(path.iterdir(), reverse=True))
                    continue
                if not stat.S_ISREG(before.st_mode):
                    rows.append({**row, 'status': 'excluded', 'reason': 'not a regular file'})
                    continue
                if before.st_size > policy['max_file_bytes'] or total + before.st_size > policy['max_total_bytes']:
                    rows.append({**row, 'status': 'skipped', 'size_bytes': before.st_size, 'reason': 'byte limit'})
                    complete = False
                    continue
                # O_NOFOLLOW also rejects a symlink swapped in after lstat.
                fd = open_file(path)
                payload = bytearray()
                digest = hashlib.sha256()
                with os.fdopen(fd, 'rb') as stream:
                    opened = os.fstat(stream.fileno())
                    if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                        raise ValueError('file changed before capture')
                    while chunk := stream.read(1048576):
                        if time.monotonic() >= deadline or len(payload) + len(chunk) > policy['max_file_bytes'] or total + len(payload) + len(chunk) > policy['max_total_bytes']:
                            raise ValueError('capture limit reached')
                        digest.update(chunk)
                        payload.extend(chunk)
                    after = os.fstat(stream.fileno())
                current = path.lstat()
                if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or (current.st_ino, current.st_mtime_ns) != (after.st_ino, after.st_mtime_ns):
                    raise ValueError('file changed during capture')
                total += len(payload)
                row.update(sha256=digest.hexdigest(), size_bytes=len(payload))
                row['change'] = 'unchanged' if previous.get(str(path), {}).get('sha256') == row['sha256'] else 'modified' if str(path) in previous else 'created'
                requested = explicit or any(path == p or path.is_relative_to(p) for p in explicit_paths)
                if phase == 'final' and (requested or row['change'] != 'unchanged' or baseline['status'] != 'complete'):
                    archive = Path(category) / f'stage-{stage}' / str(root_index) / relative
                    target = destination / archive
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(payload)
                    row.update(status='collected', archive_path=archive.as_posix(), stability='checked-before-after')
                rows.append(row)
            except (OSError, ValueError) as exc:
                rows.append({**row, 'status': 'collection_failed', 'reason': str(exc)[:500]})
                complete = False
    if phase == 'final':
        observed = {r['path'] for r in rows}
        rows.extend({'path': p, 'status': 'deleted', 'stage': stage} for p in previous if p not in observed and complete)
    if phase == 'final' and baseline['status'] != 'complete':
        complete = False
    receipt = {'schema_version': 1, 'phase': phase, 'stage': stage, 'workspace': str(workspace),
               'policy': policy, 'status': 'complete' if complete else 'partial', 'files': rows,
               'elapsed_seconds': time.monotonic() - started, 'baseline_status': baseline['status'],
               'baseline_elapsed_seconds': baseline.get('elapsed_seconds'),
               'consistency': 'per-file checks; live services are not transactionally snapshotted'}
    if phase == 'baseline':
        baseline_path.write_text(json.dumps(receipt, indent=2) + '\n')
        (destination / 'baseline.json').write_text(json.dumps(receipt, indent=2) + '\n')
    else:
        manifest_path = destination / 'manifest.json'
        earlier = json.loads(manifest_path.read_bytes()) if manifest_path.exists() else None
        if earlier and earlier.get('stage') != stage:
            receipt['files'] = earlier['files'] + receipt['files']
            if earlier['status'] != 'complete':
                receipt['status'] = 'partial'
        receipt['capture_elapsed_seconds_total'] = receipt['elapsed_seconds'] + (
            earlier.get('capture_elapsed_seconds_total', 0) if earlier and earlier.get('stage') != stage else 0)
        manifest_path.write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('baseline', 'final'), required=True)
    parser.add_argument('--policy', required=True)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--stage', type=int, required=True)
    parser.add_argument('--forbidden', default='[]')
    args = parser.parse_args()
    value = capture(Path.cwd(), args.destination, json.loads(args.policy), phase=args.phase,
                    stage=args.stage, forbidden=json.loads(args.forbidden))
    print(json.dumps({'status': value['status'], 'stage': args.stage}))


if __name__ == '__main__':
    main()
