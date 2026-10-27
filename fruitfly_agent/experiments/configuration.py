"""Read one explicit workspace experiment file; never write user configuration."""
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any
from fruitfly_agent.runtime_spec.documents import DocumentReader, mapping

from fruitfly_agent.lab.improvement.configuration import ImprovementSettings, TaskSetImprovementSettings
from fruitfly_agent.lab.rsi.configuration import EvolutionSettings
from fruitfly_agent.lab.improvement.api import ProcessAssessmentSettings, ExplorationSettings, MultiTaskSettings


def settings(cls, value, label):
    data = dict(mapping(value, {f.name for f in fields(cls)}, label))
    if issubclass(cls, ImprovementSettings) and 'components' in data:
        if not isinstance(data['components'], list):
            raise ValueError('components must be a list')
        data['components'] = tuple(data['components'])
    if cls is ProcessAssessmentSettings and 'assessors' in data:
        if not isinstance(data['assessors'], list):
            raise ValueError('assessors must be a list')
        data['assessors'] = tuple(data['assessors'])
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
    process_assessment: ProcessAssessmentSettings = field(default_factory=ProcessAssessmentSettings)
    exploration: ExplorationSettings = field(default_factory=ExplorationSettings)
    multi_task: MultiTaskSettings = field(default_factory=MultiTaskSettings)
    source_files: tuple = field(default=(), compare=False, repr=False)

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
            'process_assessment': asdict(self.process_assessment), 'exploration': asdict(self.exploration),
            'multi_task': asdict(self.multi_task)}


def load_configuration(workspace, path=None, *, overrides=None, material_only=False):
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
            'tasks': {'inline': overrides['task']}, 'comparison': {'inline': {}},
            'edit': {'base_prompt': {'fields': ['parameters.text']}}}
    else:
        raise ValueError('experiment configuration not found: ' + str(target) + '; initialize a workspace first')
    from .comparison import normalize_experiment
    raw, references, _ = normalize_experiment(document, target, material_only=material_only)
    source_files = (*reader.sources.values(), *references)
    sources = {section + '.' + name: str(target) for section, value in raw.items()
        if isinstance(value, dict) for name in value}
    for section, values in (overrides or {}).items():
        raw[section] = {**raw.get(section, {}), **values}
        sources.update({section + '.' + name: 'command line' for name in values})
    runtime = mapping(raw.get('runtime', {}), {'config', 'profile'}, 'runtime')
    models = mapping(raw.get('models', {}), {'executor', 'editor', 'assessor'}, 'models')
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
        settings(ProcessAssessmentSettings, raw.get('process_assessment', {}), 'process_assessment'),
        settings(ExplorationSettings, raw.get('exploration', {}), 'exploration'),
        MultiTaskSettings.from_dict(raw.get('multi_task', {})), source_files)
