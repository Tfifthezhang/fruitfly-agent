"""Atomic evolution records; no proposal, scoring or runtime activation."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import tempfile
from fruitfly_agent.rsi.contracts import EvolutionJob, VerificationEvidence

class EvolutionStore:
    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve()
        self.root = self.workspace / '.fruitfly/evolution'

    def path(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', job_id):
            raise ValueError('invalid evolution job id')
        path = self.root / (job_id + '.json')
        if path.is_symlink():
            raise ValueError('evolution job must not be a symlink')
        if not path.resolve().is_relative_to(self.workspace):
            raise ValueError('evolution jobs must stay inside the workspace')
        return path


    def load(self, job_id):
        path = self.path(job_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('job_id') != job_id:
            raise ValueError('evolution job identity mismatch')
        if data.get('evidence') is not None:
            data['evidence'] = VerificationEvidence(**data['evidence'])
        return EvolutionJob(**data)


    def save(self, job):
        path = self.path(job.job_id)
        self.root.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix='.evolution-', dir=self.root)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump(asdict(job), stream, ensure_ascii=False, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

