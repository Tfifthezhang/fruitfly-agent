"""Freeze actual execution, improvement and registered persistent-state material."""
from pathlib import Path
from fruitfly_agent.lab.algorithms.targets import (
    SystemVersion, SnapshotFile, StateSnapshot, canonical_json, TargetChange, VersionCandidate,
)
from fruitfly_agent.run.storage.snapshots import SnapshotStore, capture_source_tree
from fruitfly_agent.run.storage.versions import VersionStore
from fruitfly_agent.run.runtime.manifest import execution_version_payload


class RunVersions:
    def __init__(self, *, workspace, artifacts, manifest, improvement_identity, state_sources):
        self.workspace, self.artifacts = workspace, artifacts
        self.manifest, self.improvement_identity, self.state_sources = manifest, improvement_identity, state_sources
        self.snapshots = SnapshotStore(artifacts)
        self.versions = VersionStore(artifacts)

    def freeze_state(self):
        snapshots = tuple(source.freeze() for source in self.state_sources())
        return self.snapshots.put(StateSnapshot(tuple(f for s in snapshots for f in s.files),
                                               roots=tuple(r for s in snapshots for r in s.roots)))

    def freeze_source(self):
        root = Path(__file__).resolve().parents[3]
        return self.snapshots.put(capture_source_tree(root))

    def freeze(self, *, manifest=None):
        manifest = manifest if manifest is not None else self.manifest()
        source = self.freeze_source()
        harness = execution_version_payload(manifest, source)
        h = self.artifacts.put_text(canonical_json(harness)).artifact_id
        i = self.artifacts.put_text(canonical_json({"source": source, "strategy": self.improvement_identity()})).artifact_id
        version = SystemVersion(h, i, self.freeze_state())
        self.versions.put(version)
        return version

    def text_candidate(self, parent, snapshot, text):
        before = self.artifacts.put_text(snapshot.text).artifact_id
        after = self.artifacts.put_text(text).artifact_id
        import json
        harness = json.loads(self.artifacts.read_text(parent.harness))
        if snapshot.binding.kind == "prompt":
            harness["base_prompt"] = {"content_hash": after}
        else:
            harness["target_overrides"] = {snapshot.binding.key: after}
        h = self.artifacts.put_text(canonical_json(harness)).artifact_id
        candidate = VersionCandidate(parent, SystemVersion(h, parent.improver, parent.state),
            (TargetChange("H", snapshot.target_id, snapshot.schema, before, after),))
        self.versions.put_candidate(candidate)
        return candidate
