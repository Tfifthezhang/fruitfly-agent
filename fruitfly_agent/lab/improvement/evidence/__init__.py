"""Detached evidence workspaces with explicit read and candidate-write grants."""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib

from ..contracts.pipeline import (ComponentFile, HarnessSnapshot, relative_path,
                                 canonical_json, require_hash)


class MemoryArtifacts:
    """An embedding/test artifact capability; hosts supply durable storage."""
    def __init__(self):
        self.values = {}

    def put(self, content):
        if not isinstance(content, bytes):
            raise TypeError('artifact content must be bytes')
        reference = 'sha256:' + hashlib.sha256(content).hexdigest()
        self.values[reference] = content
        return reference

    def read(self, reference):
        require_hash(reference)
        content = self.values[reference]
        if 'sha256:' + hashlib.sha256(content).hexdigest() != reference:
            raise ValueError('evidence content changed')
        return content


class EvidenceWorkspace:
    """Files are copies. Only component-owned `harness/ID/` paths can mutate.

    This is a tool capability boundary, not an OS sandbox for trusted Python.
    Large text is paginated; binary originals remain available as bytes.
    """
    def __init__(self, *, baseline, files, writable_ids, record=None, max_bytes=2_000_000):
        self.baseline, self.files = baseline, dict(files)
        self.writable_ids = frozenset(writable_ids)
        self.max_bytes = max_bytes
        self.record = record or (lambda event, **fields: None)
        if self.writable_ids - {c.component_id for c in baseline.components}:
            raise ValueError('workspace scope contains an unregistered component')
        for path, content in self.files.items():
            relative_path(path)
            if not isinstance(content, bytes):
                raise TypeError('workspace files must be bytes')
        for component in baseline.components:
            for file in component.files:
                self.files[f'harness/{component.component_id}/{file.path}'] = file.text.encode('utf-8')
        if sum(map(len, self.files.values())) > max_bytes:
            raise ValueError('complete evidence workspace exceeds its byte allocation')

    @classmethod
    def build(cls, request, artifacts, *, record=None):
        from ..contracts.editing import TaskSetProposalRequest
        if isinstance(request, TaskSetProposalRequest):
            from .task_sets import build_workspace
            return build_workspace(request, artifacts, record=record)
        task, baseline = request.task, request.baseline
        files = {'context/task.md': task.instruction.encode('utf-8'),
                 'context/edit-grants.json': canonical_json({'component_ids': request.plan.component_ids,
                     'options': request.plan.component_options}).encode('utf-8')}
        for resource in task.inputs:
            files['context/inputs/' + resource.path] = artifacts.read(resource.artifact_id)
        rows = []
        for execution in request.records:
            # Measurement and verifier objects are deliberately not workspace inputs.
            rows.append(asdict(execution))
            files[f'context/executions/{execution.run_id}/output.txt'] = execution.output.encode('utf-8')
            for resource in execution.artifacts:
                files[f'context/executions/{execution.run_id}/' + resource.path] = artifacts.read(resource.artifact_id)
        files['context/executions.json'] = canonical_json(rows).encode('utf-8')
        for entry in request.experience:
            prefix = 'context/library/' + entry.entry_id
            files[prefix + '/EXPERIENCE.json'] = canonical_json(asdict(entry)).encode('utf-8')
        for index, candidate in enumerate(getattr(request, 'candidates', getattr(request, 'history', ()))):
            files[f'context/candidates/{index}/manifest.json'] = canonical_json({
                'candidate_id': candidate.candidate_id, 'base': candidate.base.to_dict(),
                'harness': candidate.harness.to_dict(), 'reasons': [asdict(r) for r in candidate.reasons]}).encode('utf-8')
            for component in candidate.harness.components:
                for file in component.files:
                    files[f'context/candidates/{index}/{component.component_id}/{file.path}'] = file.text.encode('utf-8')
        if request.plan.feedback == 'scored' and getattr(request, 'feedback', ()):
            files['context/measurements.json'] = canonical_json([asdict(m) for m in request.feedback]).encode('utf-8')
        files['INDEX.json'] = canonical_json({'files': sorted(files),
            'components': [asdict(c) for c in baseline.components],
            'writable_components': request.plan.component_ids}).encode('utf-8')
        return cls(baseline=baseline, files=files, writable_ids=request.plan.component_ids, record=record)

    def paths(self):
        return tuple(sorted(self.files))

    def read(self, path):
        relative_path(path)
        if path not in self.files:
            raise ValueError('file is outside the evidence grant')
        data = self.files[path]
        self.record('editor-read', path=path, artifact_id='sha256:' + hashlib.sha256(data).hexdigest())
        return data

    def _write_path(self, path):
        relative_path(path)
        parts = path.split('/')
        if len(parts) < 3 or parts[0] != 'harness' or parts[1] not in self.writable_ids:
            raise ValueError('only declared candidate components may be edited')

    def write(self, path, text):
        self._write_path(path)
        if not isinstance(text, str):
            raise TypeError('component source must be text')
        data = text.encode('utf-8')
        if sum(map(len, self.files.values())) - len(self.files.get(path, b'')) + len(data) > self.max_bytes:
            raise ValueError('editor workspace byte allocation exhausted')
        self.files[path] = data
        self.record('editor-write', path=path, bytes=len(data))

    def delete(self, path):
        self._write_path(path)
        if path not in self.files:
            raise ValueError('candidate file does not exist')
        del self.files[path]
        self.record('editor-delete', path=path)

    def collect(self):
        components = []
        for component in self.baseline.components:
            prefix = f'harness/{component.component_id}/'
            files = tuple(ComponentFile(path[len(prefix):], value.decode('utf-8'))
                          for path, value in self.files.items() if path.startswith(prefix))
            components.append(replace(component, files=files))
        return HarnessSnapshot(tuple(components))


__all__ = ['EvidenceWorkspace', 'MemoryArtifacts']
