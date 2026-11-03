"""Materialize owner-declared text bindings without changing the source profile."""
from pathlib import Path
from fruitfly_agent.lab.catalog import load_system_config, bind_component_changes, materialize_system


def validate_prepared_runtime(receipt):
    files = dict(receipt['runtime']['installation'].get('files', ()))
    source_root = Path(__file__).resolve().parents[2]
    from fruitfly_eval.installation import installation_identity
    expected = installation_identity(source_root)['files']
    if any(files.get(relative) != digest for relative, digest in expected):
        raise ValueError('prepared runtime lacks matching execution limits or facts (including declared parameter resources); prepare current source again')



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
        from dataclasses import replace
        profile = replace(profile, execution={**profile.execution, 'max_turns':None, 'max_tool_calls_per_turn':None})
        def read(reference):
            if reference in profile.artifact_contents:
                return profile.artifact_contents[reference]
            return (self.workspace / '.fruitfly/artifacts' / reference[7:]).read_text(encoding='utf-8')
        return materialize_system(profile, destination, artifact_reader=read, model_source=self.original_catalog)
