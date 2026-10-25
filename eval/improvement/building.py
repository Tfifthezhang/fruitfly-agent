"""Materialize owner-declared text bindings without changing the source profile."""
from pathlib import Path
import copy
import yaml
import hashlib
from fruitfly_agent.lab.improvement.api import content_hash
from fruitfly_agent.runtime_spec import HarnessProfile, apply_profile_binding


def validate_prepared_runtime(receipt):
    files = dict(receipt['runtime']['installation'].get('files', ()))
    source_root = Path(__file__).resolve().parents[2]
    for relative in ('fruitfly_agent/run/runtime/limits.py', 'fruitfly_agent/run/cli.py', 'eval/harbor_agent.py',
                     'fruitfly_agent/core/loop.py', 'fruitfly_agent/run/configuration/profile.py',
                     'fruitfly_agent/run/runtime/assembly.py', 'fruitfly_agent/runtime_spec/execution.py',
                     'fruitfly_agent/runtime_spec/profiles.py', 'fruitfly_agent/runtime_spec/selections.py', 'eval/runtime.py'):
        current = hashlib.sha256((source_root / relative).read_bytes()).hexdigest()
        if files.get(relative) != current:
            raise ValueError('prepared runtime lacks matching execution limits or facts; prepare current source again')


class RuntimeConfigBuilder:
    def __init__(self, workspace, runtime, components):
        self.workspace, self.runtime, self.components = Path(workspace), runtime, components
        config = Path(runtime.config_path or '.fruitfly/default-config.yaml')
        self.source = config if config.is_absolute() else self.workspace / config
        self.source_bytes = self.source.read_bytes()
        self.data = yaml.safe_load(self.source_bytes)
        self.profile = runtime.profile or self.data['default_profile']
        self.original_catalog = Path(self.data['profiles'][self.profile]['model']['catalog'])
        if not self.original_catalog.is_absolute():
            self.original_catalog = (self.source.parent / self.original_catalog).resolve()
        self.model_bytes = self.original_catalog.read_bytes()

    def check(self):
        if self.source.read_bytes() != self.source_bytes:
            raise ValueError('source runtime configuration changed during improvement')
        if self.original_catalog.read_bytes() != self.model_bytes:
            raise ValueError('source model catalog changed during improvement')

    def build(self, snapshot, *, destination):
        self.check()
        data = copy.deepcopy(self.data)
        profile = data['profiles'][self.profile]
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        model_path = destination.parent / 'models.yaml'
        with model_path.open('xb') as out:
            out.write(self.model_bytes)
        profile['model']['catalog'] = str(model_path)
        for binding in self.components.export(snapshot, changed_only=False):
            if not binding.text and snapshot.component(binding.component_id) == self.components.adapters[binding.component_id].snapshot():
                continue
            reference = content_hash(binding.text)
            path = self.workspace / '.fruitfly/artifacts' / reference[7:]
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.read_bytes() != binding.text.encode():
                raise ValueError('immutable component artifact mismatch')
            if not path.exists():
                with path.open('xb') as out: out.write(binding.text.encode())
            if binding.kind == 'configuration':
                # The binding changes only its declared configuration section.
                parsed = HarnessProfile('candidate', execution=profile.get('execution', {}))
                profile['execution'] = dict(apply_profile_binding(parsed, binding.kind, binding.key, binding.text).execution)
            elif binding.kind == 'prompt':
                profile['prompt'] = reference
            else:
                profile.setdefault('artifact_bindings', {})[binding.key] = reference
        with destination.open('x') as out:
            yaml.safe_dump(data, out, allow_unicode=True, sort_keys=False)
        return destination
