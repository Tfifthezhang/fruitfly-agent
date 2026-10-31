"""Task-source definitions compose native and optional benchmark capabilities."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .configuration import mapping


@dataclass
class SourceBinding:
    execution_id: str
    material_id: str = ''
    instruction: str = ''
    input_paths: tuple[str, ...] = ()
    parameters: tuple[tuple[str, Any], ...] = ()
    measured: bool = False
    config_path: Any = None
    profile: Any = None
    benchmark: Any = None
    source_identity: str = ''
    persistent_policy: str = ''
    adoption_notice: str = 'persistent adoption needs an installed task package with independent holdout'
    defaults: dict = field(default_factory=dict)
    required_components: tuple[str, ...] = ()
    forbidden_components: tuple[str, ...] = ('improvement-editor', 'improvement-evaluator')
    task_set: Any = None


def native(config):
    from fruitfly_agent.lab.improvement.tasks import TaskPackCatalog
    from fruitfly_agent.lab.improvement.materials import WorkspaceTaskSource
    from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
    task = mapping(config.task, {'source', 'instruction', 'input_paths', 'pack', 'parameters'}, 'file task')
    instruction, pack = task.get('instruction', ''), task.get('pack', '')
    paths = task.get('input_paths', [])
    if not isinstance(instruction, str) or not isinstance(pack, str) or not isinstance(paths, list):
        raise ValueError('file task needs text instruction/pack and a list of input paths')
    if pack and (instruction or paths):
        raise ValueError('a task package owns its inputs; do not override instruction or files')
    relative_paths = []
    for name in paths:
        if not isinstance(name, str) or not name.strip():
            raise ValueError('task input paths must be nonempty strings')
        declared = Path(name).expanduser()
        if not declared.is_absolute():
            declared = config.path.parent / declared
        if any(p.is_symlink() for p in (declared, *declared.parents)):
            raise ValueError('task input paths must not contain symlinks')
        relative_paths.append(str(declared.resolve().relative_to(config.workspace)))
    relative = tuple(relative_paths)
    if pack:
        catalog = TaskPackCatalog(config.workspace)
        for component in config.improvement.components or catalog.compatible_targets(pack):
            suite = catalog.freeze(pack, component)
        identity = suite.source_hash
    elif instruction.strip():
        material = WorkspaceTaskSource(config.workspace, MemoryArtifacts()).freeze('check', instruction, paths=relative)
        identity = material.material_id
    else:
        raise ValueError('select task.instruction/input_paths or an installed task.pack in experiment.yaml')
    from fruitfly_agent.lab.improvement.execution import builtin_executions
    parameters = builtin_executions().get('file-task').normalize(tuple(mapping(
        task.get('parameters', {}), {'assessment_interval', 'delivery_manifest'}, 'file execution parameters').items()))
    return SourceBinding('file-task', pack, instruction, relative, tuple(sorted(parameters.items())), bool(pack),
        source_identity=identity,
        persistent_policy='task-holdout-v1' if pack and catalog.holdout(pack) else '')


def editor(config):
    from fruitfly_agent.lab.improvement.execution import builtin_executions
    task = mapping(config.task, {'source', 'material', 'parameters'}, 'editor experiment')
    material = task.get('material')
    if not isinstance(material, str) or not material:
        raise ValueError('editor experiments require task.material')
    from fruitfly_agent.improvement.contracts.validation import identifier
    identifier(material)
    path = config.workspace / '.fruitfly/improvement/experiments' / material / 'experiment.json'
    if not path.is_file() or path.is_symlink():
        raise ValueError('installed editor experiment is missing')
    definition = builtin_executions().get('improver-comparison')
    params = task.get('parameters', {})
    if not isinstance(params, dict):
        raise ValueError('editor execution parameters must be a mapping')
    parameters = definition.normalize(tuple({'inner_strategy': 'simple', **params}.items()))
    if not parameters['inner_components'].split():
        raise ValueError('declare inner editable components')
    from types import SimpleNamespace
    from fruitfly_agent.lab.improvement.improver.materials import freeze
    from fruitfly_agent.lab.improvement.tasks import TaskPackCatalog
    frozen = freeze(SimpleNamespace(workspace=config.workspace, tasks=TaskPackCatalog(config.workspace)),
        material, parameters['inner_components'].split()[0])
    return SourceBinding('improver-comparison', material, parameters=tuple(sorted(parameters.items())), measured=True,
        source_identity=frozen.source_id, persistent_policy='improver-paired-v1',
        required_components=(), forbidden_components=())


def benchmark(config):
    import hashlib
    from fruitfly_eval.improvement.configuration import resolve_benchmark
    settings = resolve_benchmark(config)
    return SourceBinding('benchmark-task', 'benchmark-task', measured=True,
        config_path=settings.request.runtime.config_path, profile=settings.request.runtime.profile, benchmark=settings,
        source_identity=hashlib.sha256(settings.source_request.read_bytes() + settings.host_bytes).hexdigest(),
        adoption_notice='benchmark reward supports search; RSI needs a separately registered independent verifier')


SOURCES = {'files': native, 'editor': editor, 'eval': benchmark}


def task_set(config):
    from .task_sets import resolve
    return resolve(config)


SOURCES['task-set'] = task_set


def resolve_source(config, *, default_source='files'):
    source = config.task.get('source', default_source)
    if not isinstance(source, str) or source not in SOURCES:
        raise ValueError('unknown task source; choose ' + ', '.join(SOURCES))
    return SOURCES[source](config)
