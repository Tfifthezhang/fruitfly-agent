"""Durable RSI adapter over the existing improvement inbox and Application."""

from fruitfly_agent.rsi.contracts import AdoptionResult, EvolutionJob, VerificationEvidence
from fruitfly_agent.run.storage.evolution import EvolutionStore


class RunEvolutionHost:
    """Explicit opt-in host. Verification policy is supplied independently of search.

    No default autonomous policy, CLI command or model request is introduced.
    One external coordinator owns a job; uncertain interrupted costs are not replayed.
    """
    def __init__(self, *, workspace, manifest, propose, read_candidate, read_artifact,
                 prepare_candidate, activate, policy_id, verify):
        if not policy_id or not callable(verify):
            raise ValueError('an explicit independent verifier and policy identity are required')
        self.workspace = workspace
        self.manifest = manifest
        self.propose_operation = propose
        self.read_candidate = read_candidate
        self.read_artifact = read_artifact
        self.prepare_candidate = prepare_candidate
        self.activate = activate
        self.policy_id = policy_id
        self.verifier = verify
        self.store = EvolutionStore(workspace)
        self.root = self.store.root

    def active_manifest(self):
        return self.manifest()['digest']


    def load_job(self, job_id):
        return self.store.load(job_id)

    def save_job(self, job):
        self.store.save(job)

    async def propose(self, direction):
        records = await self.propose_operation(direction)
        return records[0].candidate_id if records else None

    async def verify(self, candidate_id, policy_id):
        if policy_id != self.policy_id:
            raise ValueError('verification policy mismatch')
        record = self.read_candidate(candidate_id)
        if record.parent_manifest_digest != self.active_manifest():
            raise ValueError('candidate parent version is stale')
        text = self.read_artifact(record.artifact_id)
        evidence = await self.verifier(record, text)
        self._validate_evidence(record, evidence)
        return evidence

    def _validate_evidence(self, record, evidence):
        if not isinstance(evidence, VerificationEvidence) or (
            evidence.candidate_id, evidence.artifact_id, evidence.parent_manifest_digest, evidence.policy_id
        ) != (record.candidate_id, record.artifact_id, record.parent_manifest_digest, self.policy_id):
            raise ValueError('verification must bind the exact candidate, artifact, parent and policy')

    async def adopt(self, candidate_id, evidence):
        record = self.read_candidate(candidate_id)
        self._validate_evidence(record, evidence)
        if not evidence.passed:
            return AdoptionResult('rejected')
        if self.active_manifest() != evidence.parent_manifest_digest:
            return AdoptionResult('stale')
        handle = await self.prepare_candidate(self.manifest(), candidate_id)
        await self.activate(handle, expected_manifest_digest=evidence.parent_manifest_digest)
        return AdoptionResult('activated', self.active_manifest())

    def is_active(self, candidate_id):
        record = self.read_candidate(candidate_id)
        return bool(record.activated_manifest_digest) and record.activated_manifest_digest == self.active_manifest()
