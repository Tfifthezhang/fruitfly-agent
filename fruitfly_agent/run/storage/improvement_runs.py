"""Atomic experiment summaries, scoped independently of candidate retention."""
from dataclasses import asdict
import json
import hashlib
import os
from pathlib import Path
import re
import tempfile

from fruitfly_agent.interactive.contracts.candidates import CandidateSection
from fruitfly_agent.interactive.contracts.improvement import ImprovementRunView


class ImprovementRunStore:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.root = self.workspace / '.fruitfly/improvement/runs'

    def _path(self, run_id):
        if not isinstance(run_id, str) or not re.fullmatch(r'[0-9a-f]{32}', run_id):
            raise ValueError('invalid improvement run identity')
        path = self.root / (run_id + '.json')
        if (not path.resolve().is_relative_to(self.workspace)
                or any(p.is_symlink() for p in (path, self.root, *self.root.parents)
                       if p.is_relative_to(self.workspace))):
            raise ValueError('improvement run paths must remain in the workspace without symlinks')
        return path

    def save(self, view: ImprovementRunView, scope):
        path = self._path(view.run_id)
        payload = {'schema_version': 1, 'config_path': str(scope[0]), 'profile_id': str(scope[1]),
                   'run': asdict(view)}
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                             prefix='.run-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            self._path(view.run_id)
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def list(self, scope):
        self._path('0' * 32)
        rows = []
        for path in self.root.glob('*.json'):
            self._path(path.stem)
            payload = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(payload, dict) or payload.get('schema_version') != 1:
                raise ValueError('unsupported improvement run record')
            if (payload.get('config_path'), payload.get('profile_id')) != tuple(map(str, scope)):
                continue
            value = payload.get('run')
            if not isinstance(value, dict) or value.get('run_id') != path.stem:
                raise ValueError('invalid improvement run record')
            text_fields = ('run_id', 'status', 'algorithm', 'target', 'role', 'direction',
                           'started_at', 'finished_at', 'stop_reason')
            if (any(not isinstance(value.get(name), str) for name in text_fields)
                    or value['role'] not in {'H', 'S', 'I'}
                    or value['status'] not in {'running', 'completed', 'failed', 'cancelled', 'interrupted'}
                    or not isinstance(value.get('candidate_ids'), list)
                    or any(not isinstance(v, str) or not re.fullmatch(r'[0-9a-f]{32}', v)
                           for v in value['candidate_ids'])
                    or not isinstance(value.get('sections'), list)):
                raise ValueError('invalid improvement run fields')
            evidence = value.get('evidence', [])
            if not isinstance(evidence, list) or any(not isinstance(pair, list) or len(pair) != 2
                    or any(not isinstance(v, str) for v in pair) for pair in evidence):
                raise ValueError('invalid improvement run evidence')
            sections = []
            for section in value['sections']:
                if (not isinstance(section, dict)
                        or any(not isinstance(section.get(name), str) for name in ('title', 'text', 'summary'))
                        or not isinstance(section.get('initial'), bool)):
                    raise ValueError('invalid improvement run section')
                sections.append(CandidateSection(**section))
            rows.append(ImprovementRunView(**{**value, 'sections': tuple(sections),
                'candidate_ids': tuple(value['candidate_ids']),
                'evidence': tuple(tuple(pair) for pair in evidence)}))
        return tuple(sorted(rows, key=lambda row: (row.started_at, row.run_id), reverse=True))

    def logs(self, run_id, scope):
        row = next((row for row in self.list(scope) if row.run_id == run_id), None)
        if row is None:
            raise ValueError('experiment does not belong to this configuration/profile')
        evidence = dict(row.evidence)
        if evidence.get('Workflow journal'):
            path = self.workspace / evidence['Workflow journal']
            owned = self.workspace / '.fruitfly/improvement/jobs'
            if (path.name != 'events.jsonl' or path.parent.parent != owned
                    or any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(self.workspace))):
                raise ValueError('workflow journal must remain in its owned directory')
            data = path.read_bytes()
            if 'sha256:' + hashlib.sha256(data).hexdigest() != evidence.get('Workflow journal hash'):
                raise ValueError('workflow journal hash mismatch')
            return data.decode('utf-8')
        if not evidence.get('Search history'):
            return 'No search journal was produced. Inspect the result for setup or execution errors.'
        path = self.workspace / evidence['Search history']
        if (path.is_symlink() or path.resolve().parent != self.workspace / '.fruitfly/improvement/searches'
                or any(p.is_symlink() for p in path.parents if p.is_relative_to(self.workspace))):
            raise ValueError('search journal must remain in its owned workspace directory')
        data = path.read_bytes()
        if 'sha256:' + hashlib.sha256(data).hexdigest() != evidence.get('Search history hash'):
            raise ValueError('search journal hash mismatch')
        return data.decode('utf-8')
