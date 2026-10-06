"""Reference-aware compaction of Run-owned optimization outputs.

Scan before mutation. Unknown/malformed reference files prevent deletion.
Only artifacts owned by removed candidate records are eligible for collection.
"""
import json
import os
from pathlib import Path
import re
import yaml


_HASH = re.compile(r'sha256:[0-9a-f]{64}')
_ID = re.compile(r'[0-9a-f]{32}')


def compact_candidates(workspace, store, config_path):
    workspace = Path(workspace).resolve()
    if not store.root.is_relative_to(workspace) or not store.artifacts.root.is_relative_to(workspace):
        return ()
    records = store.list()
    if not records:
        return ()
    protected_ids, references, paths, config_refs = set(), set(), set(), set()

    def walk(value, *, evolution=False, config=False):
        if isinstance(value, dict):
            for child in value.values():
                walk(child, evolution=evolution, config=config)
        elif isinstance(value, (list, tuple)):
            for child in value:
                walk(child, evolution=evolution, config=config)
        elif isinstance(value, str):
            if _HASH.fullmatch(value):
                references.add(value)
                if config:
                    config_refs.add(value)
            if evolution and _ID.fullmatch(value):
                protected_ids.add(value)
            if '.fruitfly/optimization/' in value:
                path = Path(value)
                paths.add((workspace / path).resolve() if not path.is_absolute() else path.resolve())

    # Configs may live outside the workspace; include the active one explicitly.
    configs = {Path(config_path)}
    for root, dirs, files in os.walk(workspace, followlinks=False):
        dirs[:] = [d for d in dirs if d not in {'.venv', '__pycache__', 'node_modules', '.git'}
                   and not (Path(root) / d).is_symlink()]
        for name in files:
            if name.endswith(('.yaml', '.yml')):
                configs.add(Path(root) / name)
    try:
        for path in configs:
            if path.exists():
                if path.is_symlink():
                    return ()
                walk(yaml.safe_load(path.read_text()), config=True)
        for directory, evolution in (('sessions', False), ('evolution', True)):
            for path in (workspace / '.fruitfly' / directory).rglob('*'):
                if path.is_symlink():
                    return ()
                if path.is_file() and path.suffix in {'.json', '.jsonl'}:
                    if path.suffix == '.jsonl':
                        for line in path.read_text().splitlines():
                            if line.strip():
                                walk(json.loads(line), evolution=evolution)
                    else:
                        walk(json.loads(path.read_text()), evolution=evolution)
    except (OSError, ValueError, yaml.YAMLError):
        return ()

    keep, seen, selected = set(protected_ids), set(), set()
    for record in records:  # newest first, across algorithms
        scope = (record.config_path, record.profile_id, record.target, record.task_pack_id)
        # Legacy attribution is unknown: preserve until a runtime can identify it.
        if not record.config_path:
            keep.add(record.candidate_id)
        elif scope not in seen:
            seen.add(scope)
            keep.add(record.candidate_id)
        if record.artifact_id in config_refs and (*scope, record.artifact_id) not in selected:
            keep.add(record.candidate_id)
            selected.add((*scope, record.artifact_id))
    removed = [r for r in records if r.candidate_id not in keep]
    for record in records:
        if record.candidate_id in keep:
            references.update((record.artifact_id, record.parent_target_reference))
            walk(dict(record.evidence))
    for record in removed:
        store._path(record.candidate_id).unlink()
    # Never sweep arbitrary artifacts: only text owned by obsolete records.
    eligible = {ref for r in removed for ref in (r.artifact_id, r.parent_target_reference)}
    for ref in eligible - references:
        if _HASH.fullmatch(ref):
            path = store.artifacts.root / ref.removeprefix('sha256:')
            if not path.is_symlink():
                path.unlink(missing_ok=True)
    # Delete obsolete evidence only if no retained record/session/job refers to it.
    for record in removed:
        for label, value in record.evidence:
            if label not in {'Search history', 'Task snapshot'}:
                continue
            raw = workspace / value
            if raw.is_symlink() or any(p.is_symlink() for p in raw.parents if p != workspace):
                continue
            path = raw.resolve()
            directory = 'searches' if label == 'Search history' else 'task-snapshots'
            suffix = '.jsonl' if label == 'Search history' else '.json'
            allowed = workspace / '.fruitfly' / 'optimization' / directory
            if path.parent == allowed and path.suffix == suffix and path not in paths and path.is_file():
                path.unlink()
    return tuple(r.candidate_id for r in removed)
