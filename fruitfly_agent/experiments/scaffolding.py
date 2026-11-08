"""Create private workspace inputs from installed, public templates only."""
from importlib.resources import files
import json
import os
from pathlib import Path
from typing import Any
from fruitfly_agent.run.configuration.scaffolding import system_templates


def _template(name: str) -> str:
    return files('fruitfly_agent.experiments').joinpath('templates', name).read_text(encoding='utf-8')


def workspace_templates(*, source: str | None = None, benchmark: str | None = None,
                        variant: str = 'smoke') -> dict[str, str]:
    """Render inputs without reading local settings, credentials or machine state."""
    if source not in {None, 'task-set'}:
        raise ValueError('init supports system configuration or --source task-set')
    if source is None and (benchmark is not None or variant != 'smoke'):
        raise ValueError('--benchmark and --variant require --source task-set')
    result = dict(system_templates())
    if source == 'task-set':
        result['experiment.yaml'] = _template('task-set.yaml')
        result['tasks/tb4-smoke.yaml'] = _template('tasks/tb4-smoke.yaml')
        if not benchmark:
            raise ValueError('--source task-set requires --benchmark with a registered catalog ID')
        # Eval remains optional. Descriptor lookup does not invoke preflight or Harbor.
        from fruitfly_eval.catalog import builtin_catalog
        from fruitfly_eval.contracts import EvaluationRequest
        descriptor = builtin_catalog().get(benchmark).descriptor
        if variant not in {item.variant_id for item in descriptor.variants}:
            raise ValueError('benchmark does not declare variant: ' + variant)
        request = EvaluationRequest.from_dict({
            
            'runtime': {'working_directory': '.'},
            'benchmark': {'id': benchmark, 'variant': variant},
            'execution': {'attempts': 1, 'concurrency': 1, 'timeout_seconds': 3600},
        })
        result['eval-request.json'] = json.dumps(request.to_dict(), indent=2) + '\n'
        result['eval-host.yaml'] = _template('eval-host.yaml')
    return result


def initialize_workspace(workspace: Path, *, source: str | None = None,
                         benchmark: str | None = None, variant: str = 'smoke') -> dict[str, Any]:
    """Reuse shared models/secrets, refuse config collisions, undo partial writes."""
    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        raise ValueError('create the workspace directory before init: ' + str(workspace))
    payloads = workspace_templates(source=source, benchmark=benchmark, variant=variant)
    directory = workspace / '.fruitfly'
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ValueError('.fruitfly must be a real workspace directory')
    preserved = []
    models = directory / 'models.yaml'
    if models.is_symlink() or (models.exists() and not models.is_file()):
        raise ValueError('models.yaml must be a regular file')
    if models.exists():
        payloads.pop('models.yaml')
        preserved.append(str(models))
    conflicts = [name for name in payloads if (directory / name).exists() or (directory / name).is_symlink()]
    if conflicts:
        raise ValueError('init will not overwrite existing configuration: ' + ', '.join(conflicts))
    for name in payloads:
        parent = (directory / name).parent
        while parent != directory:
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise ValueError('configuration parent must be a real directory: ' + str(parent))
            parent = parent.parent
    secret = directory / 'secrets.env'
    if secret.is_symlink() or (secret.exists() and not secret.is_file()):
        raise ValueError('secrets.env must be a regular file')
    if secret.exists():
        preserved.append(str(secret))
    else:
        payloads['secrets.env'] = '# Set the key privately here, or export it in the process environment.\nDEEPSEEK_API_KEY=\n'
    created: list[tuple[Path, int, int]] = []
    made_directory = False
    created_directories = []
    try:
        if not directory.exists():
            directory.mkdir(mode=0o700)
            made_directory = True
        for name, contents in payloads.items():
            target = directory / name
            missing = []
            parent = target.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for parent in reversed(missing):
                parent.mkdir(mode=0o700)
                created_directories.append(parent)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                identity = os.fstat(handle.fileno())
                created.append((target, identity.st_dev, identity.st_ino))
                handle.write(contents)
    except BaseException:
        for target, device, inode in reversed(created):
            try:
                identity = target.lstat()
                if (identity.st_dev, identity.st_ino) == (device, inode):
                    target.unlink()
            except OSError:
                pass
        for parent in reversed(created_directories):
            try:
                parent.rmdir()
            except OSError:
                pass
        if made_directory:
            try:
                directory.rmdir()
            except OSError:
                pass
        raise
    steps = [
        'Review the shared .fruitfly/models.yaml; select its model aliases and H/S/I in default-config.yaml. Registered defaults are owner resources; use an explicit component document for customization.',
        'Set DEEPSEEK_API_KEY privately in .fruitfly/secrets.env or the process environment.',
    ]
    if source == 'task-set':
        steps += [
            'Prepare a complete Linux Python and Agent venv; set FRUITFLY_EVAL_PYTHON_ROOT and FRUITFLY_EVAL_VENV for eval-host.yaml.',
            'Run eval prepare --tasks-only, then eval prepare through fruitfly-agent-lab (downloads/containers; no model calls).',
        ]
    if source == 'task-set':
        steps.append('Use a stage research document; inspect with improvement show, then explicitly improvement step (model/container work; charges may apply).')
    else:
        steps.append('System configuration is ready. For Improvement, register a task backend through the embedding API or initialize a separate benchmark workspace with --source task-set --benchmark ID.')
    return {'workspace': str(workspace), 'source': source or 'system',
        'created': [str(path) for path, _, _ in created], 'preserved': preserved, 'next_steps': steps}
