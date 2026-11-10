"""Portable research publications sharing one explicitly selected artifact root."""
import json
from pathlib import Path
from fruitfly_agent.improvement.contracts.bundles import ResearchBundle
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.versions import canonical_json
from .artifacts import DataArtifactStore
from .research import ResearchStore


class ArtifactPort:
    def __init__(self, store):
        self.store = store

    def put(self, content):
        return self.store.put_bytes(content).artifact_id

    def read(self, reference):
        return self.store.read_bytes(reference)


class ResearchOutputs:
    def __init__(self, workspace, study, root=None):
        self.workspace = Path(workspace).resolve()
        self.root = Path(root).resolve() if root else self.workspace / '.fruitfly/improvement/jobs' / study
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise ValueError('research output root must not be a symlink')
        self.artifacts = DataArtifactStore(self.root / 'artifacts')
        self.study = study

    def journal(self):
        return ResearchStore(self.workspace, self.study, directory=self.root)

    def write(self, relative, value):
        from fruitfly_agent.improvement.contracts.validation import relative_path
        relative_path(relative)
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValueError('research output must not be a symlink')
        from fruitfly_agent.run.configuration.persistence import write_bytes
        write_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode())
        return path

    def inputs(self, values, kind):
        resources, producers = [], []
        for index, value in enumerate(values):
            if value.startswith('sha256:'):
                resources.append(Resource('input-' + str(index) + '.json', value, 'application/json'))
                continue
            path = Path(value).resolve()
            if path.is_dir():
                path = path / 'bundle.json'
            bundle = ResearchBundle.from_dict(json.loads(path.read_text()))
            # Portable bundles carry a root locator separate from immutable content.
            locator = json.loads(path.with_name('location.json').read_text())
            source_root = (path.parent / locator['root']).resolve()
            source = DataArtifactStore(source_root / 'artifacts')
            if source_root != self.root:
                for reference in bundle.dependencies:
                    self.artifacts.put_bytes(source.read_bytes(reference))
            producers.append({'bundle': bundle.identity, 'producer': bundle.producer,
                'configuration_id': bundle.configuration_id})
            selected = bundle.outputs
            if bundle.kind != 'organize':
                selected = tuple(resource for resource in bundle.outputs if resource.path == bundle.primary_path)
                if len(selected) != 1:
                    raise ValueError('bundle is missing its typed primary output: ' + bundle.primary_path)
            for resource in selected:
                self.artifacts.put_bytes(source.read_bytes(resource.artifact_id))
                resources.append(resource)
        # Different batches commonly use the same logical output name.
        used, normalized = set(), []
        from dataclasses import replace
        for i, resource in enumerate(resources):
            logical_path = resource.path if resource.path not in used else 'inputs/' + str(i) + '/' + resource.path
            used.add(logical_path); normalized.append(replace(resource, path=logical_path))
        return tuple(normalized), producers

    def publish(self, kind, run_id, result, inputs, configuration_id):
        # Follow only immutable references actually present in stored JSON. Raw
        # logs remain bytes; this never interprets their instructions or conclusions.
        import re
        pending = [r.artifact_id for r in (*result.outputs, *inputs)] + [configuration_id]
        visited = set()
        def refs(value):
            if isinstance(value, dict):
                for child in value.values(): yield from refs(child)
            elif isinstance(value, (list, tuple)):
                for child in value: yield from refs(child)
            elif isinstance(value, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', value):
                yield value
        while pending:
            reference = pending.pop()
            if reference in visited or not reference: continue
            try:
                data = self.artifacts.read_bytes(reference)
            except ValueError as exc:
                if not isinstance(exc.__cause__, FileNotFoundError):
                    raise
                continue  # Content identities such as task hashes need no stored bytes.
            visited.add(reference)
            try: pending.extend(refs(json.loads(data)))
            except (ValueError, UnicodeDecodeError): pass
        bundle = ResearchBundle(kind, run_id, result.outputs, tuple(r.artifact_id for r in inputs),
            configuration_id, tuple(sorted(visited)))
        prefix = {'import': 'inputs/historical-eval', 'organize': 'evidence', 'propose': 'candidates',
            'assess': 'assessments', 'compare': 'comparisons'}.get(kind, 'results')
        prefix += '/' + run_id if kind != 'import' else '/' + run_id
        path = self.write(prefix + '/bundle.json', bundle.to_dict())
        import os
        self.write(prefix + '/location.json', {'root': os.path.relpath(self.root, path.parent)})
        for resource in result.outputs:
            try: content = json.loads(self.artifacts.read_bytes(resource.artifact_id))
            except (ValueError, UnicodeDecodeError): continue
            self.write(prefix + '/' + resource.path, content)
        return bundle, path
