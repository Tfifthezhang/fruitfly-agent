"""Durable RSI adapter over the existing optimization inbox and Application."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import tempfile

from fruitfly_agent.lab.algorithms.evolution import AdoptionResult, EvolutionJob, VerificationEvidence


class RunEvolutionHost:
    """Explicit opt-in host. Verification policy is supplied independently of search.

    No default autonomous policy, CLI command or model request is introduced.
    One external coordinator owns a job; uncertain interrupted costs are not replayed.
    """
    def __init__(self, application, factory, *, policy_id, verify):
        if not policy_id or not callable(verify):
            raise ValueError('an explicit independent verifier and policy identity are required')
        self.application = application
        self.factory = factory
        self.policy_id = policy_id
        self.verifier = verify
        self.root = factory.cwd / '.fruitfly' / 'evolution'

    def active_manifest(self):
        return self.application.runtime_manifest['digest']

    def _path(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', job_id):
            raise ValueError('invalid evolution job id')
        path = self.root / (job_id + '.json')
        if path.is_symlink():
            raise ValueError('evolution job must not be a symlink')
        if not path.resolve().is_relative_to(self.factory.cwd):
            raise ValueError('evolution jobs must stay inside the workspace')
        return path

    def load_job(self, job_id):
        path = self._path(job_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('job_id') != job_id:
            raise ValueError('evolution job identity mismatch')
        if data.get('evidence') is not None:
            data['evidence'] = VerificationEvidence(**data['evidence'])
        return EvolutionJob(**data)

    def save_job(self, job):
        path = self._path(job.job_id)
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

    async def propose(self, direction):
        records = await self.application.optimize(direction)
        return records[0].candidate_id if records else None

    async def verify(self, candidate_id, policy_id):
        if policy_id != self.policy_id:
            raise ValueError('verification policy mismatch')
        record = self.factory.candidate_store.read(candidate_id)
        if record.parent_manifest_digest != self.active_manifest():
            raise ValueError('candidate parent version is stale')
        text = self.factory.artifact_store.read_text(record.artifact_id)
        evidence = await self.verifier(record, text)
        self._validate_evidence(record, evidence)
        return evidence

    def _validate_evidence(self, record, evidence):
        if not isinstance(evidence, VerificationEvidence) or (
            evidence.candidate_id, evidence.artifact_id, evidence.parent_manifest_digest, evidence.policy_id
        ) != (record.candidate_id, record.artifact_id, record.parent_manifest_digest, self.policy_id):
            raise ValueError('verification must bind the exact candidate, artifact, parent and policy')

    async def adopt(self, candidate_id, evidence):
        record = self.factory.candidate_store.read(candidate_id)
        self._validate_evidence(record, evidence)
        if not evidence.passed:
            return AdoptionResult('rejected')
        if self.active_manifest() != evidence.parent_manifest_digest:
            return AdoptionResult('stale')
        handle = await self.factory.prepare_candidate(self.application.runtime_manifest, candidate_id)
        await self.application.activate_runtime(handle, expected_manifest_digest=evidence.parent_manifest_digest)
        return AdoptionResult('activated', self.active_manifest())

    def is_active(self, candidate_id):
        record = self.factory.candidate_store.read(candidate_id)
        return bool(record.activated_manifest_digest) and record.activated_manifest_digest == self.active_manifest()
