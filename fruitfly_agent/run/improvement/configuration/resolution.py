"""Derive complete configurations and grants through their existing owners."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import shutil
import hashlib
import yaml

from fruitfly_agent.lab.catalog import (builtin_catalog, load_system_config,
    materialize_system, configuration_resources, optimization_grants, edit_grants)
from fruitfly_agent.run.configuration.resolution import model_catalog_path


def merge_profile(base, changes):
    """Mappings merge recursively; sequences and scalar values replace exactly."""
    result = deepcopy(base)
    for name, value in changes.items():
        if isinstance(value, dict) and isinstance(result.get(name), dict):
            result[name] = merge_profile(result[name], value)
        else:
            result[name] = deepcopy(value)
    return result


def derive_configuration(document, baseline, workspace):
    changes = deepcopy(document.raw.get('overrides', {}))
    if not isinstance(changes, dict):
        raise ValueError('overrides must use the ordinary system profile mapping')
    executor = document.raw.get('roles', {}).get('executor')
    if not changes and not executor:
        return baseline
    from fruitfly_agent.run.extensions import configured_extensions
    path = document.resolve(baseline['config'])
    extensions = configured_extensions(path, profile_id=baseline.get('profile'))
    catalog = extensions.catalog(builtin_catalog()) if extensions.registrations else builtin_catalog()
    profile = load_system_config(path, catalog=catalog).select(baseline.get('profile'))
    if executor and (executor != profile.model_profile or
            'executor' in changes.get('models', {}).get('roles', {})):
        changes = merge_profile(changes, {'models': {'roles': {'executor': executor}}})
    if not changes:
        return baseline
    destination = document.root / 'configuration' / 'derived'
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination) as temporary:
        root = Path(temporary)
        source = materialize_system(profile, root / 'source' / 'config.yaml', catalog=catalog,
            artifact_reader=lambda ref: profile.artifact_contents.get(ref) or
                (Path(workspace) / '.fruitfly/artifacts' / ref[7:]).read_text(),
            model_source=model_catalog_path(profile, path),
            resources=configuration_resources(profile, catalog, workspace))
        before = source.read_bytes()
        raw = yaml.safe_load(source.read_text())
        raw['profiles'][profile.profile_id] = merge_profile(raw['profiles'][profile.profile_id], changes)
        source.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))
        derived = load_system_config(source, catalog=catalog).select(profile.profile_id)
        from fruitfly_agent.improvement.contracts.versions import content_hash, canonical_json
        identity = content_hash(canonical_json({'origin': profile.to_dict(references=False),
            'overrides': changes, 'profile': derived.to_dict(references=False),
            'models': model_catalog_path(derived, source).read_text()}))[7:]
        final = destination / identity / 'config.yaml'
        if not final.exists():
            assembled = root / 'assembled'
            materialize_system(derived, assembled / 'config.yaml', catalog=catalog,
                model_source=model_catalog_path(derived, source),
                artifact_reader=lambda ref: derived.artifact_contents[ref],
                resources=configuration_resources(derived, catalog, workspace))
            shutil.copytree(source.parent, assembled / 'origin')
            (assembled / 'origin/config.yaml').write_bytes(before)
            (assembled / 'requested-profile.yaml').write_bytes(source.read_bytes())
            receipt = json.loads((assembled / 'snapshot.json').read_text())
            for entry in receipt['sources']:
                if entry['path'] == str(source):
                    entry['path'] = 'requested-profile.yaml'
            (assembled / 'snapshot.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
            from fruitfly_agent.improvement.contracts.configuration import configuration_differences
            changes_report = configuration_differences(yaml.safe_load(before),
                yaml.safe_load((assembled / 'config.yaml').read_text()))
            (assembled / 'human-changes.json').write_text(json.dumps(changes_report, ensure_ascii=False, indent=2))
            # Publish the complete derived bundle atomically. A concurrent
            # identical derivation may already have published the same identity.
            try:
                assembled.rename(final.parent)
            except OSError:
                if not final.exists():
                    raise
        receipt = json.loads((final.parent / 'snapshot.json').read_text())
        if hashlib.sha256(final.read_bytes()).hexdigest() != receipt['config_sha256']:
            raise ValueError('derived configuration integrity failure')
    return {'config': str(final), 'profile': derived.profile_id}


def resolve_optimization(document, profile, catalog):
    from fruitfly_agent.runtime_spec.documents import mapping
    settings = mapping(document.raw.get('optimization', {}), {'scope', 'include', 'exclude'}, 'optimization')
    scope = settings.get('scope', 'defaults')
    if scope not in {'defaults', 'explicit'}:
        raise ValueError('optimization.scope must be defaults or explicit')
    grants = optimization_grants(profile, catalog) if scope == 'defaults' else {}
    include = settings.get('include', {})
    if not isinstance(include, dict):
        raise ValueError('optimization.include must map components to field grants')
    if include:
        grants.update(edit_grants(profile, include, catalog))
    excluded = settings.get('exclude', [])
    if not isinstance(excluded, list) or any(not isinstance(name, str) for name in excluded):
        raise ValueError('optimization.exclude must list component IDs')
    for name in excluded:
        grants.pop(name, None)
    if not grants:
        raise ValueError('no selected optimization fields')
    return grants
