"""Materialize owner-declared text bindings without changing the source profile."""
from pathlib import Path
import hashlib
from fruitfly_agent.lab.catalog import load_system_config, bind_component_changes, materialize_system


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
        self.baseline = load_system_config(self.source).select(runtime.profile)
        self.profile = self.baseline.profile_id
        self.original_catalog = Path(self.baseline.model_catalog)
        if not self.original_catalog.is_absolute():
            self.original_catalog = (self.source.parent / self.original_catalog).resolve()
        self.model_bytes = self.original_catalog.read_bytes()

    def check(self):
        for source in self.baseline.source_files:
            source.check()
        if self.source.read_bytes() != self.source_bytes:
            raise ValueError('source runtime configuration changed during improvement')
        if self.original_catalog.read_bytes() != self.model_bytes:
            raise ValueError('source model catalog changed during improvement')

    def build(self, snapshot, *, destination):
        self.check()
        bindings = []
        for binding in self.components.export(snapshot, changed_only=False):
            if not binding.text and snapshot.component(binding.component_id) == self.components.adapters[binding.component_id].snapshot():
                continue
            bindings.append(binding)
        profile = bind_component_changes(self.baseline, bindings)
        def read(reference):
            if reference in profile.artifact_contents:
                return profile.artifact_contents[reference]
            return (self.workspace / '.fruitfly/artifacts' / reference[7:]).read_text(encoding='utf-8')
        return materialize_system(profile, destination, artifact_reader=read, model_source=self.original_catalog)
