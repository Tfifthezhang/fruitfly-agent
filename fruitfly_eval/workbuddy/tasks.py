"""Freeze complete dataset resources while selecting exact WorkBuddy task identities."""
from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import tomllib
from typing import Any, Callable

from fruitfly_eval.benchmarks.base import BenchmarkDescriptor
from fruitfly_eval.harbor.material import tree_identity


def validate_tree(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError('dataset root must be a real directory')
    resolved = root.resolve()
    for entry in root.rglob('*'):
        if entry.is_symlink() and not entry.resolve().is_relative_to(resolved):
            raise ValueError('dataset link escapes declared resources: ' + str(entry.relative_to(root)))
        if not entry.is_dir() and not entry.is_file():
            raise ValueError('unsupported dataset resource: ' + str(entry.relative_to(root)))


def inventory(root: Path, descriptor: BenchmarkDescriptor, variant: str, *,
              inspect_resources: Callable[[dict[str, Any]], dict[str, Any]],
              excluded: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    validate_tree(root)
    dataset_path = root / 'dataset.toml'
    if not dataset_path.is_file():
        raise ValueError('WorkBuddy datasets require dataset.toml and tasks/; select the dataset root')
    dataset = tomllib.loads(dataset_path.read_text())
    selection = next((v for v in descriptor.variants if v.variant_id == variant), None)
    if selection is None:
        raise ValueError('unknown benchmark variant')
    rows = []
    for path in sorted((root / 'tasks').glob('*/task.toml')):
        config = tomllib.loads(path.read_text())
        name = config.get('task', {}).get('name') or path.parent.name
        if not isinstance(name, str) or not name or '/' in name or '\\' in name or name in {'.', '..'}:
            raise ValueError('WorkBuddy task names must be exact nonempty local names')
        if selection.task_names and name not in selection.task_names:
            if excluded is not None:
                excluded.append({'id': name, 'reason': 'outside declared smoke selection'})
            continue
        instruction = path.parent / 'instruction.md'
        if not instruction.is_file():
            raise ValueError('selected task has no instruction.md: ' + name)
        row = {'id': name, 'name': name, 'path': str(path.parent.resolve()), 'configuration': config}
        requirements = inspect_resources(row)
        if variant == 'no_gpu' and requirements['gpu_requirements']:
            if excluded is not None:
                excluded.append({'id': name, 'reason': 'effective GPU or unresolved resource requirements',
                                 'requirements': requirements['gpu_requirements']})
            continue
        rows.append({**row, 'sha256': tree_identity(path.parent), 'requirements': requirements})
    names = [r['id'] for r in rows]
    if not rows or len(names) != len(set(names)):
        raise ValueError('dataset selection is empty or has ambiguous task names')
    if selection.task_names and set(names) != set(selection.task_names):
        raise ValueError('smoke task is absent from the declared dataset')
    verifier = dataset.get('verifier', {})
    if verifier.get('engine') == 'composite' and not (root / 'shared/verifier/plugin.py').is_file():
        raise ValueError('composite verifier requires the dataset-local shared/verifier/plugin.py')
    return rows


def freeze_dataset(root: Path, cache: Path, descriptor: BenchmarkDescriptor, variant: str, *,
                   inspect_resources: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    """Keep dataset.toml/shared resources beside tasks; never edit the input dataset."""
    root = root.absolute()
    inventory(root, descriptor, variant, inspect_resources=inspect_resources)
    identity = tree_identity(root)
    destination = cache / 'datasets' / identity / root.name
    if destination.resolve().is_relative_to(root.resolve()):
        raise ValueError('dataset cache must be outside the input dataset')
    if not destination.exists():
        destination.parent.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.dataset-', dir=destination.parent.parent) as temporary:
            staged = Path(temporary) / identity
            staged.mkdir()
            shutil.copytree(root, staged / root.name, symlinks=True)
            validate_tree(staged / root.name)
            if tree_identity(staged / root.name) != identity or tree_identity(root) != identity:
                raise ValueError('dataset changed while freezing')
            try:
                staged.rename(destination.parent)
            except FileExistsError:
                pass
    validate_tree(destination)
    if tree_identity(destination) != identity:
        raise ValueError('frozen dataset changed; preserve the source and prepare new material')
    return {'root': str(destination), 'original': str(root), 'sha256': identity,
            'dataset': descriptor.dataset, 'variant': variant,
            'tasks': inventory(destination, descriptor, variant, inspect_resources=inspect_resources)}


def check_dataset(receipt: dict[str, Any], descriptor: BenchmarkDescriptor, variant: str, *,
                  inspect_resources: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    root = Path(receipt['root'])
    validate_tree(root)
    if receipt['dataset'] != descriptor.dataset or receipt['variant'] != variant:
        raise ValueError('prepared dataset identity differs from the request')
    if tree_identity(root) != receipt['sha256']:
        raise ValueError('prepared dataset or shared verifier resources changed')
    rows = inventory(root, descriptor, variant, inspect_resources=inspect_resources)
    if receipt.get('task_names'):
        from fruitfly_eval.task_selection import select_prepared_tasks
        rows = select_prepared_tasks({'id': receipt['sha256'], 'tasks': rows}, tuple(receipt['task_names']))['tasks']
    if rows != receipt['tasks']:
        raise ValueError('prepared task inventory changed')
