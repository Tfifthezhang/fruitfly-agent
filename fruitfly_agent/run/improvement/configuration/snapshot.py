"""Freeze safe effective research configuration and informational differences."""
from dataclasses import asdict
import json
import re
import yaml
from fruitfly_agent.improvement.contracts.configuration import configuration_differences


def redact(value):
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if re.search(r'(^|_)(api_key|password|secret|access_token|authorization)$', k, re.I)
                    and not k.endswith('_env') else redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [redact(v) for v in value]
    return value


def snapshot(config=None, roles=None, *, action, inputs=(), parameters=None):
    result = {'action': action, 'inputs': list(inputs), 'parameters': parameters or {},
        'unknown': [], 'comparison_policy': 'Report differences; do not gate research continuation.'}
    if config is not None:
        result['experiment'] = config.snapshot()
        result['authored'] = redact(yaml.safe_load(config.path.read_text()))
    if roles is not None:
        result['system'] = roles.profile.to_dict(references=False)
        result['model_roles'] = {**roles.profile.resolved_model_roles(roles.profile.model_profile),
            **roles.overrides}
        result['effective'] = {'runtime': roles.profile.to_runtime_dict(),
            'settings': roles.profile.component_settings,
            'models': {k: asdict(v) for k, v in roles.specs.items()}}
        result['sources'] = [{'path': s.path, 'sha256': s.digest} for s in roles.profile.source_files]
    return redact(result)


def differences(outputs, current, producers):
    result = []
    for producer in producers:
        reference = producer.get('configuration_id')
        if reference:
            before = json.loads(outputs.artifacts.read_bytes(reference))
            result.append({'producer': producer['producer'], 'changes': configuration_differences(before, current)})
    return result


def export_candidates(outputs, directory, result, reporting):
    """Use the ordinary Catalog materializer for complete reviewable candidates."""
    from pathlib import Path
    from fruitfly_agent.lab.catalog import bind_component_changes, materialize_system, configuration_resources
    from fruitfly_agent.improvement.contracts.candidates import CandidateBundle
    proposal = json.loads(outputs.artifacts.read_bytes(result.outputs[0].artifact_id))
    profile, catalog, components = (reporting[k] for k in ('profile', 'catalog', 'components'))
    resources = configuration_resources(profile, catalog, outputs.workspace)
    for index, value in enumerate(proposal['candidates']):
        candidate = CandidateBundle.from_dict(value)
        root = Path(directory) / candidate.candidate_id
        root.mkdir(parents=True, exist_ok=True)
        for name, selected in (('baseline', profile), ('candidate', bind_component_changes(profile,
                components.export(candidate.harness), catalog=catalog))):
            materialize_system(selected, root / name / 'config.yaml', catalog=catalog,
                artifact_reader=reporting['artifact_reader'], model_source=reporting['model_source'], resources=resources)
        (root / 'changes.json').write_text(json.dumps({'changed_ids': candidate.changed_ids,
            'base': candidate.base.to_dict(), 'harness': candidate.harness.to_dict()}, ensure_ascii=False, indent=2))
        (root / 'rationale.json').write_text(json.dumps(value['reasons'], ensure_ascii=False, indent=2))
        source_config = reporting.get('system_source')
        origin = Path(source_config).parent / 'origin' if source_config else None
        if origin is not None and not (origin.parent / 'human-changes.json').is_file():
            origin = None
        human = []
        if origin is not None and (origin / 'config.yaml').exists():
            import shutil
            shutil.copytree(origin, root / 'origin')
            human = json.loads((origin.parent / 'human-changes.json').read_text())
        (root / 'human-changes.json').write_text(json.dumps(human, ensure_ascii=False, indent=2))
        before = root / ('origin' if origin is not None and (origin / 'config.yaml').exists() else 'baseline') / 'config.yaml'
        total = configuration_differences(yaml.safe_load(before.read_text()),
            yaml.safe_load((root / 'candidate/config.yaml').read_text()))
        (root / 'total-changes.json').write_text(json.dumps(total, ensure_ascii=False, indent=2))
