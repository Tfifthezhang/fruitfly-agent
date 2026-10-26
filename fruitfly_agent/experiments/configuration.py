"""Read one explicit workspace experiment file; never write user configuration."""
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any
import yaml
from fruitfly_agent.runtime_spec.documents import DocumentReader

from fruitfly_agent.lab.improvement.configuration import ImprovementSettings, TaskSetImprovementSettings
from fruitfly_agent.lab.rsi.configuration import EvolutionSettings
from fruitfly_agent.lab.improvement.api import ProcessAssessmentSettings, ExplorationSettings, MultiTaskSettings


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError('configuration keys must be distinct strings')
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def mapping(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(label + ' contains unknown fields or is not a mapping')
    return value


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


def load_configuration(workspace, path=None, *, overrides=None):
    workspace = Path(workspace).resolve()
    target = Path(path).expanduser() if path is not None else workspace / '.fruitfly/experiment.yaml'
    if not target.is_absolute():
        target = workspace / target
    target = target.resolve()
    if path is not None and not target.is_file():
        raise ValueError('experiment configuration not found: ' + str(target))
    raw = {}
    sources = {}
    source_files: tuple = ()
    if target.is_file():
        reader = DocumentReader()
        raw = reader.read(target)
        if isinstance(raw, dict) and type(raw.get('schema_version')) is int and raw['schema_version'] == 2:
            from .comparison import normalize_experiment
            raw, source_files, _ = normalize_experiment(raw, target)
        source_files = (*reader.sources.values(), *source_files)
        mapping(raw, {'schema_version', 'task', 'runtime', 'models', 'improvement', 'rsi', 'stop',
            'process_assessment', 'exploration', 'multi_task'}, 'experiment')
        if type(raw.get('schema_version')) is not int or raw['schema_version'] != 1:
            raise ValueError('experiment requires schema_version 1')
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
