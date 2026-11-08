"""Resolve explicit named research inputs; no stages or Providers are invoked."""
from dataclasses import dataclass
import json
from pathlib import Path
from .configuration import ResearchDocument


@dataclass(frozen=True)
class ResearchContext:
    document: ResearchDocument
    stage: str
    inputs: dict
    settings: dict
    branch: str

    @classmethod
    def resolve(cls, path, stage=None):
        document = ResearchDocument(path)
        selected = stage or document.next['stage']
        if selected != document.next['stage']:
            raise ValueError('stage differs from next.stage; edit next to select its named inputs')
        from fruitfly_agent.runtime_spec.documents import mapping
        inputs = mapping(document.next.get('inputs', {}),
            {'harness', 'batches', 'evidence', 'assessments'}, 'next.inputs')
        resolved = {}
        index_path = document.root / 'references.json'
        index = json.loads(index_path.read_text()) if index_path.exists() else {}
        def reference(value, *, harness=False):
            mapping(value, {'artifact', 'bundle', 'candidate', 'config'}, 'input reference')
            if len(value) != 1:
                raise ValueError('input reference requires exactly one selector')
            kind, name = next(iter(value.items()))
            if kind == 'config':
                if not harness:
                    raise ValueError('config references are only valid for harness inputs')
                resolved['harness_configuration'] = str(document.resolve(name))
                return resolved['harness_configuration']
            if kind == 'bundle':
                path = document.resolve(name)
                if harness:
                    configs = list(path.parent.glob('*/candidate/config.yaml'))
                    if len(configs) == 1:
                        resolved['harness_configuration'] = str(configs[0])
                return str(path)
            key = document.research.get('branch', 'main') + ':' + name
            if key not in index:
                raise ValueError('unknown branch artifact: ' + name)
            row = index[key]
            if harness and row.get('candidate_config'):
                resolved['harness_configuration'] = str((document.root / row['candidate_config']).resolve())
                resolved['harness_bundle'] = str((document.root / row['bundle']).resolve())
            field = 'candidate_config' if kind == 'candidate' else 'bundle'
            if harness and selected == 'execute':
                field = 'bundle'
            if not row.get(field):
                raise ValueError('reference has no ' + field + ': ' + name)
            return str((document.root / row[field]).resolve())
        for name, value in inputs.items():
            resolved[name] = reference(value, harness=True) if name == 'harness' else [reference(item) for item in value]
        resolved['context'] = [reference(item) for item in document.next.get('context', [])]
        required = {'eval': (), 'import': (), 'organize': ('batches',), 'assess': ('batches',),
            'propose': ('batches',), 'execute': ('harness',), 'compare': ('batches',)}[selected]
        for name in required:
            if not resolved.get(name):
                raise ValueError(selected + ' requires next.inputs.' + name)
        if selected == 'compare' and len(resolved['batches']) < 2:
            raise ValueError('compare requires at least two batches')
        return cls(document, selected, resolved, document.settings(selected), document.research.get('branch', 'main'))

    def preview(self):
        from .configuration.snapshot import redact
        return redact({'research': self.document.research, 'stage': self.stage,
            'inputs': self.inputs, 'settings': self.settings,
            'roles': self.document.raw.get('roles', {}),
            'baseline': self.document.raw.get('baseline'),
            'optimization': self.document.raw.get('optimization', {}),
            'overrides': self.document.raw.get('overrides', {}),
            'observed': self.document.raw.get('observed', {})})
