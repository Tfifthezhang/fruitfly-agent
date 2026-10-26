"""Freeze actual execution, improvement and registered persistent-state material."""
from pathlib import Path
from fruitfly_agent.lab.algorithms.targets import (
    SystemVersion, SnapshotFile, StateSnapshot, canonical_json, TargetChange, VersionCandidate, state_artifact_path, target_edits,
)
from fruitfly_agent.run.storage.snapshots import SnapshotStore, capture_source_tree
from fruitfly_agent.run.storage.versions import VersionStore
from fruitfly_agent.run.runtime.manifest import execution_version_payload


class RunVersions:
    def __init__(self, *, workspace, artifacts, manifest, improvement_identity, state_sources,
                 restore_improvement_identity=None):
        self.workspace, self.artifacts = workspace, artifacts
        self.manifest, self.improvement_identity, self.state_sources = manifest, improvement_identity, state_sources
        self.restore_improvement_identity = restore_improvement_identity
        self.snapshots = SnapshotStore(artifacts)
        self.versions = VersionStore(artifacts)

    def freeze_state(self, manifest=None):
        manifest = manifest if manifest is not None else self.manifest()
        bindings = {a['key']: a['id'] for a in manifest.get('data_artifacts', ()) if a.get('role') == 'S'}
        sources = tuple(self.state_sources())
        registered = {source.artifact_key for source in sources if getattr(source, 'artifact_key', None)}
        if set(bindings) - registered:
            raise ValueError('state artifact has no registered snapshot source')
        snapshots = tuple(source.freeze_text(self.artifacts.read_text(bindings[source.artifact_key]))
                          if getattr(source, 'artifact_key', None) in bindings else source.freeze()
                          for source in sources)
        files: dict[str, SnapshotFile] = {}
        for snapshot in snapshots:
            for entry in snapshot.files:
                if entry.path in files and files[entry.path] != entry:
                    raise ValueError('registered state sources disagree on a shared file')
                files[entry.path] = entry
        return self.snapshots.put(StateSnapshot(tuple(files.values()),
                                               roots=tuple(sorted({r for s in snapshots for r in s.roots}))))

    def freeze_source(self):
        root = Path(__file__).resolve().parents[3]
        return self.snapshots.put(capture_source_tree(root))

    def freeze(self, *, manifest=None):
        manifest = manifest if manifest is not None else self.manifest()
        source = self.freeze_source()
        harness = execution_version_payload(manifest, source)
        h = self.artifacts.put_text(canonical_json(harness)).artifact_id
        identity = self.improvement_identity()
        if self.restore_improvement_identity is not None:
            for artifact in manifest.get('data_artifacts', ()):
                if artifact.get('role') == 'I':
                    identity = self.restore_improvement_identity(identity, artifact['key'],
                        self.artifacts.read_text(artifact['id']))
        i = self.artifacts.put_text(canonical_json({"source": source, "strategy": identity,
            "artifacts": sorted((a for a in manifest.get("data_artifacts", ()) if a.get("role") == "I"), key=lambda a: a["key"])})).artifact_id
        version = SystemVersion(h, i, self.freeze_state(manifest))
        self.versions.put(version)
        return version

    def text_candidate(self, parent, snapshot, text):
        if snapshot.binding.kind == 'components':
            edits = target_edits(snapshot, text)
            if not edits:
                raise ValueError('a component candidate must change at least one component')
            current, changes = parent, []
            for part, value in edits:
                candidate = self.text_candidate(current, part, value)
                current = candidate.version
                changes.extend(candidate.changes)
            candidate = VersionCandidate(parent, current, tuple(changes))
            self.versions.put_candidate(candidate)
            return candidate
        if snapshot.role not in {'H', 'S', 'I'} or (snapshot.role in {'S', 'I'} and snapshot.binding.kind != 'artifact'):
            raise ValueError('no version adapter for this role and binding')
        before = self.artifacts.put_text(snapshot.text).artifact_id
        after = self.artifacts.put_text(text).artifact_id
        if snapshot.role == 'S':
            state = self.snapshots.read(parent.state)
            path = state_artifact_path(snapshot.binding.key)
            original = next((f for f in state.files if f.path == path), None)
            if original is None or original.digest != before:
                raise ValueError('state target has no matching registered immutable document')
            updated = StateSnapshot(tuple(SnapshotFile(f.path, text) if f.path == path else f
                                          for f in state.files), state.update_rule, state.roots)
            candidate = VersionCandidate(parent, SystemVersion(parent.harness, parent.improver,
                self.snapshots.put(updated)), (TargetChange('S', snapshot.target_id, snapshot.schema, before, after),))
            self.versions.put_candidate(candidate)
            return candidate
        if snapshot.role == 'I':
            import json
            payload = json.loads(self.artifacts.read_text(parent.improver))
            if self.restore_improvement_identity is not None:
                payload['strategy'] = self.restore_improvement_identity(payload['strategy'], snapshot.binding.key, text)
            payload['artifacts'] = sorted([a for a in payload.get('artifacts', ()) if a['key'] != snapshot.binding.key] + [
                {'key': snapshot.binding.key, 'id': after, 'role': 'I', 'media_type': 'application/json',
                 'size_bytes': len(text.encode('utf-8'))}], key=lambda a: a['key'])
            identity = self.artifacts.put_text(canonical_json(payload)).artifact_id
            candidate = VersionCandidate(parent, SystemVersion(parent.harness, identity, parent.state),
                (TargetChange('I', snapshot.target_id, snapshot.schema, before, after),))
            self.versions.put_candidate(candidate)
            return candidate
        import json
        harness = json.loads(self.artifacts.read_text(parent.harness))
        if snapshot.binding.kind == 'configuration':
            from fruitfly_agent.runtime_spec import HarnessProfile, apply_profile_binding
            profile = apply_profile_binding(HarnessProfile('candidate'), snapshot.binding.kind, snapshot.binding.key, text)
            harness['execution'] = dict(profile.execution)
        elif snapshot.binding.kind == "prompt":
            harness["base_prompt"] = {"content_hash": after}
        else:
            artifacts = [a for a in harness.get('data_artifacts', ()) if a.get('key') != snapshot.binding.key]
            artifacts.append({'key': snapshot.binding.key, 'id': after,
                'media_type': 'text/plain; charset=utf-8', 'size_bytes': len(text.encode('utf-8'))})
            harness['data_artifacts'] = sorted(artifacts, key=lambda a: a['key'])
        h = self.artifacts.put_text(canonical_json(harness)).artifact_id
        candidate = VersionCandidate(parent, SystemVersion(h, parent.improver, parent.state),
            (TargetChange("H", snapshot.target_id, snapshot.schema, before, after),))
        self.versions.put_candidate(candidate)
        return candidate
