"""Read one explicit workspace experiment file; never write user configuration."""
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any
from fruitfly_agent.runtime_spec.documents import DocumentReader, mapping

from fruitfly_agent.lab.improvement.configuration import ImprovementSettings, TaskSetImprovementSettings
from fruitfly_agent.lab.rsi.configuration import EvolutionSettings
from fruitfly_agent.lab.improvement.task_sets import MultiTaskSettings


def settings(cls, value, label):
    data = dict(mapping(value, {f.name for f in fields(cls)}, label))
    if issubclass(cls, ImprovementSettings) and 'components' in data:
        if not isinstance(data['components'], list):
            raise ValueError('components must be a list')
        data['components'] = tuple(data['components'])
    return cls(**data)


@dataclass(frozen=True)
class ExperimentConfig:
    workspace: Path
    path: Path
    task: dict[str, Any] = field(default_factory=dict)
    runtime: dict[str, Any] = field(default_factory=dict)
    models: dict[str, str] = field(default_factory=dict)
    improvement: ImprovementSettings = field(default_factory=ImprovementSettings)
    rsi: EvolutionSettings = field(default_factory=EvolutionSettings)
    stop: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    multi_task: MultiTaskSettings = field(default_factory=MultiTaskSettings)
    evidence_settings: dict = field(default_factory=dict)
    source_files: tuple = field(default=(), compare=False, repr=False)
    runtime_override: bool = False

    def resolve(self, value: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError('configuration path must be a nonempty string')
        path = Path(value).expanduser()
        return (path if path.is_absolute() else self.path.parent / path).resolve()

    def snapshot(self):
        return {'schema_version': 1, 'defaults_version': 'experiment-defaults-v4',
            'workspace': str(self.workspace), 'configuration': str(self.path),
            'task': self.task, 'runtime': self.runtime, 'models': self.models,
            'improvement': asdict(self.improvement), 'rsi': asdict(self.rsi),
            'stop': self.stop, 'sources': self.sources,
            'multi_task': asdict(self.multi_task), 'evidence_settings': self.evidence_settings,
            'runtime_override': self.runtime_override}


def load_configuration(workspace, path=None, *, overrides=None, material_only=False, stage=None):
    workspace = Path(workspace).resolve()
    target = Path(path).expanduser() if path is not None else workspace / '.fruitfly/experiment.yaml'
    if not target.is_absolute():
        target = workspace / target
    target = target.resolve()
    if path is not None and not target.is_file():
        raise ValueError('experiment configuration not found: ' + str(target))
    reader = DocumentReader()
    if target.is_file():
        document = reader.read(target)
    elif path is None and (overrides or {}).get('task'):
        document = {'baseline': {'config': 'default-config.yaml'},
            'tasks': {'inline': overrides['task']}} 
    else:
        raise ValueError('experiment configuration not found: ' + str(target) + '; initialize a workspace first')
    research_document = None
    if 'research' in document:
        from fruitfly_agent.run.improvement.configuration import ResearchDocument
        research_document = ResearchDocument(target)
        document = research_document.experiment(stage or research_document.next['stage'])
        selected_stage = stage or research_document.next['stage']
        if selected_stage in {'propose', 'execute'} and research_document.next.get('inputs', {}).get('harness'):
            from fruitfly_agent.run.improvement.context import ResearchContext
            resolved = ResearchContext.resolve(target, selected_stage).inputs
            selected = resolved.get('harness_configuration', resolved['harness'])
            if not selected.endswith(('.yaml', '.yml')):
                raise ValueError('proposal harness must select a candidate configuration')
            document['baseline'] = {'config': selected}
        from fruitfly_agent.run.improvement.configuration.resolution import derive_configuration
        document['baseline'] = derive_configuration(research_document, document['baseline'], workspace)
    from .comparison import normalize_experiment
    raw, references, _ = normalize_experiment(document, target, material_only=material_only, stage=stage)
    if research_document is not None:
        raw['models'] = {**raw.get('models', {}), **research_document.raw.get('roles', {})}
        if selected_stage in {'execute', 'eval'}:
            # Executor selection is projected into the complete system profile;
            # future auxiliary-role selections do not constrain task execution.
            raw['models'] = {}
    source_files = (*reader.sources.values(), *references)
    sources = {section + '.' + name: str(target) for section, value in raw.items()
        if isinstance(value, dict) for name in value}
    for section, values in (overrides or {}).items():
        raw[section] = {**raw.get(section, {}), **values}
        sources.update({section + '.' + name: 'command line' for name in values})
    runtime = mapping(raw.get('runtime', {}), {'config', 'profile'}, 'runtime')
    models = mapping(raw.get('models', {}), {'executor', 'editor', 'assessor', 'organizer'}, 'models')
    if any(not isinstance(v, str) or not v.strip() for v in (*runtime.values(), *models.values())):
        raise ValueError('runtime and model selections must be nonempty strings')
    task = raw.get('task', {})
    if not isinstance(task, dict):
        raise ValueError('task must be a mapping')
    stop = mapping(raw.get('stop', {}), {'improvement', 'rsi'}, 'stop')
    return ExperimentConfig(workspace, target, task, runtime, models,
        settings(TaskSetImprovementSettings if task.get('source') == 'task-set' else ImprovementSettings,
            raw.get('improvement', {}), 'improvement'),
        settings(EvolutionSettings, raw.get('rsi', {}), 'rsi'), stop, sources,
        MultiTaskSettings.from_dict(raw.get('multi_task', {})),
        raw.get('evidence_settings', {}), source_files, runtime_override=research_document is not None)
