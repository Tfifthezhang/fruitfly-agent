"""Readable latest outputs grouped by task; input packages stay immutable."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


def save_task_result(workspace, record, text):
    if not record.task_pack_id:
        return None
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', record.task_pack_id) or record.task_pack_id in {'.', '..'}:
        raise ValueError('invalid result task identity')
    root = Path(workspace).resolve()
    scope = hashlib.sha256(json.dumps([record.config_path, record.profile_id], ensure_ascii=False).encode()).hexdigest()[:16]
    directory = root / '.fruitfly/optimization/task-results' / record.task_pack_id / scope / record.target
    if not directory.resolve().is_relative_to(root) or any(p.is_symlink() for p in (directory, *directory.parents) if p != root):
        raise ValueError('task results must stay in their workspace directory')
    if "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest() != record.artifact_id:
        raise ValueError("task result text does not match candidate identity")
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in (('latest.txt', text), ('latest.json', json.dumps(asdict(record), ensure_ascii=False, indent=2))):
        path = directory / name
        if path.is_symlink():
            raise ValueError('task result must not be a symlink')
        fd, temporary = tempfile.mkstemp(prefix='.result-', dir=directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return directory
