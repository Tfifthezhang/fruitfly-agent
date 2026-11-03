"""Declared package-resource inventory shared by frozen source consumers."""
from pathlib import Path, PurePosixPath
import re


def safe_resource_path(name):
    path = PurePosixPath(name)
    if not name or not path.parts or path.is_absolute() or '..' in path.parts or '\\' in name or str(path) != name:
        raise ValueError('installation file must have a canonical relative path: ' + name)
    return path


def excluded_resource(path):
    return (any(part.startswith('.') or part == '__pycache__' for part in path.parts)
            or path.suffix in {'.pyc', '.pyo'} or path.name == 'secrets.env'
            or (path.name == 'models.yaml' and
                path.as_posix() != 'fruitfly_agent/run/configuration/templates/models.yaml'))


def validate_resource_file(root, name):
    current = Path(root)
    for part in safe_resource_path(name).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('installation material cannot contain symlinks: ' + name)
    if not current.is_file():
        raise ValueError('incomplete FruitFlyAgent source: ' + name)


def declared_resource_files(root, package_data, packages):
    """Expand only build-declared resources; never discover workspace state."""
    root = Path(root)
    if not isinstance(package_data, dict):
        raise ValueError('package-data must declare package resource patterns')
    selected = set()
    for package, patterns in package_data.items():
        if not isinstance(patterns, list) or not patterns or any(not isinstance(p, str) for p in patterns):
            raise ValueError('package-data requires nonempty resource pattern lists')
        if package == '*':
            directories = tuple(path.parent for name in packages
                for path in (root / name).rglob('__init__.py')
                if not excluded_resource(PurePosixPath(path.relative_to(root).as_posix())))
        else:
            if not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', package) or package.split('.')[0] not in packages:
                raise ValueError('package-data must belong to FruitFlyAgent or Eval')
            directories = (root.joinpath(*package.split('.')),)
        for pattern in patterns:
            safe_resource_path(pattern)
            matched = []
            for directory in directories:
                for path in directory.glob(pattern):
                    if not path.is_file() and not path.is_symlink():
                        continue
                    name = path.relative_to(root).as_posix()
                    if excluded_resource(PurePosixPath(name)):
                        raise ValueError('package resource selects excluded local state: ' + name)
                    validate_resource_file(root, name)
                    matched.append(name)
            if not matched and not any(character in pattern for character in '*?['):
                raise ValueError(f'missing declared package resource: {package}/{pattern}')
            selected.update(matched)
    return tuple(sorted(selected))
