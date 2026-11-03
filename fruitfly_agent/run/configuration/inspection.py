"""Inspect one registered system without creating clients, Sessions or artifacts."""
import argparse
import json
from pathlib import Path

from fruitfly_agent.lab.catalog import builtin_catalog, load_system_config, configuration_inventory
from fruitfly_agent.providers.registry import load_model_specs
from fruitfly_agent.lab.catalog import role_alias


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
    roles = catalog.resolve_model_roles(profile.mechanisms, profile.resolved_model_roles(executor))
    for alias in roles.values():
        if alias not in models:
            raise ValueError('unknown model catalog profile: ' + alias)
    requirements = []
    for item in catalog.resolve(profile.mechanisms):
        for role, requirement in item.definition.model_role_parameters.items():
            requirements.append({'component': item.definition.descriptor.mechanism_id, 'role': role,
                'parameter': requirement.parameter, 'purpose': requirement.purpose,
                'active': requirement.required_when(item.parameters),
                'alias': role_alias(role, requirement, item.parameters, roles),
                'fallback_role': requirement.fallback_role, 'lazy': requirement.lazy})
    artifact_root = path.parent / 'artifacts' if path.parent.name == '.fruitfly' else path.parent / '.fruitfly/artifacts'
    return {'configuration': str(path), 'profile': profile.profile_id,
            'models': {role: {'alias': alias, 'binding': profile.model_roles.get(role, alias), 'model': models[alias].model,
                'sdk': models[alias].provider.sdk, 'protocol': models[alias].provider.protocol,
                'service': models[alias].service,
                'parameters': dict(models[alias].parameters), 'transport': dict(models[alias].transport)}
                for role, alias in roles.items()},
            'model_requirements': requirements,
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
