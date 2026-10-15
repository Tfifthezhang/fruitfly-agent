"""Persist verified H/I/S bindings without deciding experiment quality."""
import json
from fruitfly_agent.lab.algorithms.targets import SystemVersion, VersionCandidate, canonical_json


class VersionStore:
    def __init__(self, artifacts):
        self.artifacts = artifacts

    def put(self, version: SystemVersion) -> str:
        for reference in (version.harness, version.improver, version.state):
            self.artifacts.read_text(reference)
        return self.artifacts.put_text(canonical_json(version.to_dict())).artifact_id

    def read(self, reference: str) -> SystemVersion:
        version = SystemVersion.from_dict(json.loads(self.artifacts.read_text(reference)))
        if version.version_id != reference:
            raise ValueError("system version identity mismatch")
        return version

    def put_candidate(self, candidate: VersionCandidate) -> str:
        self.put(candidate.parent)
        self.put(candidate.version)
        for change in candidate.changes:
            self.artifacts.read_text(change.before)
            self.artifacts.read_text(change.after)
        return self.artifacts.put_text(canonical_json(candidate.to_dict())).artifact_id

    def read_candidate(self, reference: str) -> VersionCandidate:
        candidate = VersionCandidate.from_dict(json.loads(self.artifacts.read_text(reference)))
        if candidate.candidate_id != reference:
            raise ValueError("version candidate identity mismatch")
        return candidate
