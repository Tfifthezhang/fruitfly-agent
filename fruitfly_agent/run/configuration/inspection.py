"""Inspect one registered system without creating clients, Sessions or artifacts."""
import argparse
import json
from pathlib import Path

from fruitfly_agent.lab.catalog import builtin_catalog, load_system_config, configuration_inventory
from fruitfly_agent.providers.registry import load_model_specs


def inspect_configuration(path, *, profile_id=None, catalog=None):
    catalog = catalog or builtin_catalog()
    path = Path(path).resolve()
    profile = load_system_config(path, catalog=catalog).select(profile_id)
    models_path = Path(profile.model_catalog)
    models_path = models_path if models_path.is_absolute() else path.parent / models_path
    models = load_model_specs(models_path)
    executor = profile.model_profile
    if executor is None:
        if len(models) != 1:
            raise ValueError('select one executor model catalog profile')
        executor = next(iter(models))
    roles = {**profile.model_roles, 'executor': executor}
    for alias in roles.values():
        if alias not in models:
            raise ValueError('unknown model catalog profile: ' + alias)
    artifact_root = path.parent / 'artifacts' if path.parent.name == '.fruitfly' else path.parent / '.fruitfly/artifacts'
    return {'configuration': str(path), 'profile': profile.profile_id,
            'models': {role: {'alias': alias, 'model': models[alias].model} for role, alias in roles.items()},
            'components': configuration_inventory(profile, catalog,
                artifact_reader=lambda reference: (artifact_root / reference[7:]).read_text(encoding='utf-8')),
            'sources': [{'path': source.path, 'sha256': source.digest} for source in profile.source_files],
            'model_connectivity': 'not checked'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('.fruitfly/config.yaml'))
    parser.add_argument('--profile')
    args = parser.parse_args()
    try:
        print(json.dumps(inspect_configuration(args.config, profile_id=args.profile), ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, 'error: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
