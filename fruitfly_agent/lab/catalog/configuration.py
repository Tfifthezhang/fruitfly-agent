"""Pure owner-declared configuration projection shared by all runtime consumers."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
from typing import Callable

from fruitfly_agent.runtime_spec import HarnessConfig, MechanismSelection
from fruitfly_agent.runtime_spec.components import ComponentConfiguration
from fruitfly_agent.runtime_spec.profiles import load_harness_config, DEFAULT_PROMPT_ID


@dataclass(frozen=True)
class ConfigurationSurface:
    id: str
    role: str
    binding: str
    key: str
    normalize: Callable
    encode: Callable = lambda parameters: parameters['text']
    decode: Callable = lambda text: {'text': text}
    edit_options: Callable | None = None
    restore: Callable = lambda parameters, text: json.loads(text)
    allow_disabled: bool = False
    default: Callable | None = None
    reference: Callable | None = None

    def __post_init__(self):
        if (not isinstance(self.id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', self.id)
                or self.role not in {'H', 'S', 'I'}
                or self.binding not in {'prompt', 'artifact', 'configuration', 'settings'}):
            raise ValueError('configuration surface needs a stable ID, H/S/I role and supported binding')
        if self.binding != 'prompt' and not self.key:
            raise ValueError('configuration binding requires an owned key')
        if any(not callable(value) for value in (self.normalize, self.encode, self.decode, self.restore)):
            raise TypeError('configuration surface operations must be callable')
        if self.edit_options is not None and not callable(self.edit_options):
            raise TypeError('configuration edit normalizer must be callable')
        if self.default is not None and not callable(self.default):
            raise TypeError('configuration default must be callable')
        if self.reference is not None and not callable(self.reference):
            raise TypeError('configuration reference must be callable')


def configuration_surfaces(catalog):
    surfaces = {}
    for definition in catalog.definitions():
        for surface in definition.configuration_surfaces:
            if surface.id in surfaces:
                raise ValueError('duplicate configuration surface: ' + surface.id)
            surfaces[surface.id] = (definition.descriptor.mechanism_id, surface)
    return surfaces


def configure_profile(profile, catalog):
    """Validate and project documents without constructing clients or writing files."""
    if not profile.component_documents or profile.configured:
        return profile
    surfaces = configuration_surfaces(catalog)
    selections, deferred = [], []
    result = replace(profile, artifact_contents={}, artifact_bindings={}, component_settings={},
                     prompt=DEFAULT_PROMPT_ID, execution={})
    for document in profile.component_documents:
        if document.implementation in surfaces:
            deferred.append(document)
            continue
        definition = catalog.get(document.implementation)
        if document.id != document.implementation or document.role != definition.configuration_role:
            raise ValueError('component does not match its registered ID/role: ' + document.id)
        if set(document.parameters) & set(definition.model_role_parameters.values()):
            raise ValueError('bind component model aliases through system models.roles: ' + document.id)
        if definition.validate_parameters:
            definition.validate_parameters(document.parameters)
        definition.descriptor.normalize_parameters(document.parameters)
        parameters = dict(document.parameters)
        for role, field in definition.model_role_parameters.items():
            if role in profile.model_roles:
                if field in parameters and parameters[field] != profile.model_roles[role]:
                    raise ValueError('conflicting model role binding: ' + role)
                parameters[field] = profile.model_roles[role]
        selections.append(MechanismSelection(document.implementation, document.enabled, parameters))
        if set(document.artifacts) - definition.artifact_slots:
            raise ValueError('component artifacts have no registered owner: ' + document.id)
        for key, text in document.artifacts.items():
            if not document.enabled and definition.prepare_targets is None:
                continue
            reference = 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest()
            result = replace(result, artifact_bindings={**result.artifact_bindings, key: reference},
                             artifact_contents={**result.artifact_contents, reference: text})
    result = replace(result, mechanisms=tuple(selections))
    for document in deferred:
        owner, surface = surfaces[document.implementation]
        if document.id != surface.id or document.role != surface.role or (not document.enabled and not surface.allow_disabled):
            raise ValueError('configuration surface must match its registered enabled ID/role: ' + document.id)
        parameters = surface.normalize(dict(document.parameters))
        if not document.enabled:
            result = replace(result, mechanisms=(*result.mechanisms, MechanismSelection(owner, False)))
            continue
        if document.artifacts:
            if surface.binding != 'artifact' or set(document.artifacts) != {surface.key}:
                raise ValueError('surface artifact slots differ from the registered binding: ' + document.id)
            raw = document.artifacts[surface.key]
            if surface.normalize(surface.decode(raw)) != parameters:
                raise ValueError('component artifact differs from its configured value: ' + document.id)
            reference = 'sha256:' + hashlib.sha256(raw.encode()).hexdigest()
            result = replace(result, artifact_bindings={**result.artifact_bindings, surface.key: reference},
                             artifact_contents={**result.artifact_contents, reference: raw})
        if surface.binding == 'settings' and document.id in result.artifact_bindings:
            parameters = surface.normalize(surface.restore(parameters,
                result.artifact_contents[result.artifact_bindings[document.id]]))
        if surface.binding == 'configuration':
            result = replace(result, **{surface.key: parameters})
        elif surface.binding == 'settings':
            result = replace(result, component_settings={**result.component_settings, surface.key: parameters})
        else:
            text = surface.encode(parameters)
            if surface.binding == 'artifact' and surface.key in result.artifact_bindings:
                original = result.artifact_contents[result.artifact_bindings[surface.key]]
                if surface.normalize(surface.decode(original)) != parameters:
                    raise ValueError('conflicting configured artifact values: ' + document.id)
                text = original
            reference = 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest()
            contents = {**result.artifact_contents, reference: text}
            if surface.binding == 'prompt':
                builtin = surface.reference(parameters) if surface.reference is not None else None
                result = replace(result, prompt=builtin or reference, artifact_contents=contents)
            elif surface.binding == 'artifact':
                derived = (surface.default is not None and not document.artifacts
                    and surface.key not in result.artifact_bindings
                    and parameters == surface.normalize(surface.default()))
                if not derived:
                    result = replace(result, artifact_bindings={**result.artifact_bindings, surface.key: reference},
                                     artifact_contents=contents)
            else:
                raise ValueError('unsupported registered configuration binding')
        # A virtual surface may require a real owner; explicit documents never
        # silently enable missing environment/tool dependencies.
        if surface.binding in {'artifact', 'settings'} and not any(s.mechanism_id == owner for s in result.mechanisms):
            result = replace(result, mechanisms=(*result.mechanisms, MechanismSelection(owner, surface.binding != 'settings')))
    catalog.resolve(result.mechanisms)
    return replace(result, configured=True)


def load_system_config(path, *, catalog=None):
    if catalog is None:
        from .builtins import builtin_catalog
        catalog = builtin_catalog()
    config = load_harness_config(path)
    return replace(config, profiles={key: configure_profile(value, catalog) for key, value in config.profiles.items()})


def edit_grants(profile, grants, catalog):
    """Normalize owner-declared field grants without encoding component IDs in hosts."""
    from fruitfly_agent.runtime_spec.documents import mapping
    surfaces = configuration_surfaces(catalog)
    options = {}
    if not isinstance(grants, dict) or not grants:
        raise ValueError('experiment edit must select at least one component')
    for name, grant in grants.items():
        mapping(grant, {'fields', 'bounds'}, 'component edit grant')
        fields, bounds = grant.get('fields'), grant.get('bounds', {})
        if (not isinstance(fields, list) or not fields or any(not isinstance(v, str) for v in fields)
                or len(set(fields)) != len(fields) or not isinstance(bounds, dict) or set(bounds) - set(fields)):
            raise ValueError('edit grant needs distinct fields and bounds for selected fields')
        normalize = surfaces[name][1].edit_options if name in surfaces else catalog.get(name).configuration_edit
        if normalize is None:
            raise ValueError('component has no registered field editing adapter: ' + name)
        value = normalize(fields, bounds)
        if value:
            options[name] = value
    return options


def text_edit_options(fields, bounds):
    if fields != ['parameters.text'] or bounds:
        raise ValueError('text component permits only parameters.text without numeric bounds')
    return {}


def configuration_inventory(profile, catalog, *, artifact_reader=None):
    """Report configured/default values and declaration support without assembly."""
    surfaces = configuration_surfaces(catalog)
    profile = component_profile(profile, catalog, artifact_reader=artifact_reader)
    result = []
    for document in profile.component_documents:
        if document.implementation in surfaces:
            owner, surface = surfaces[document.implementation]
            effective = surface.normalize(dict(document.parameters))
            editable = surface.edit_options is not None
        else:
            definition = catalog.get(document.implementation)
            owner = definition.descriptor.mechanism_id
            effective = definition.descriptor.normalize_parameters(document.parameters)
            editable = definition.configuration_edit is not None
        def fields(value, prefix='parameters'):
            return {key: entry for name, item in value.items()
                for key, entry in (fields(item, prefix + '.' + name).items() if isinstance(item, dict)
                                   else [(prefix + '.' + name, item)])}
        authored = fields(dict(document.parameters))
        origin = document.source or 'generated inline configuration'
        definition = catalog.get(owner)
        provenance = {key: {'effective': value, 'configured': key in authored,
            'origin': origin + ':' + key if key in authored else 'registered default: ' + owner}
            for key, value in fields(effective).items()}
        result.append({'id': document.id, 'role': document.role, 'implementation': document.implementation,
                       'owner': owner, 'enabled': document.enabled,
                       'configured': dict(document.parameters), 'effective': effective,
                       'source': origin, 'fields': provenance,
                       'implementation_id': definition.implementation_id,
                       'resource_capture': 'registered' if definition.configuration_snapshot else 'no local resource capture declared',
                       'field_editing_declared': editable, 'authorized': False,
                       'artifacts': {key: 'sha256:' + hashlib.sha256(text.encode()).hexdigest()
                                     for key, text in document.artifacts.items()}})
    return result


def component_profile(profile, catalog, *, artifact_reader=None):
    """Express current effective bindings as the same public component documents."""
    surfaces = configuration_surfaces(catalog)
    documents = {d.id: d for d in profile.component_documents}
    def read(reference):
        if reference in profile.artifact_contents:
            text = profile.artifact_contents[reference]
        else:
            if artifact_reader is None:
                raise ValueError('component artifact reader is required: ' + reference)
            text = artifact_reader(reference)
        if 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest() != reference:
            raise ValueError('component artifact content differs from reference: ' + reference)
        return text
    roles = dict(profile.model_roles)
    for selection in profile.mechanisms:
        definition = catalog.get(selection.mechanism_id)
        artifacts = {key: read(profile.artifact_bindings[key]) for key in definition.artifact_slots
                     if key in profile.artifact_bindings and (selection.enabled or definition.prepare_targets)}
        parameters = dict(selection.parameters)
        for role, field in definition.model_role_parameters.items():
            alias = parameters.pop(field, None)
            if alias:
                roles[role] = alias
        fresh = ComponentConfiguration(selection.mechanism_id,
            definition.configuration_role, selection.mechanism_id, parameters, selection.enabled,
            artifacts=artifacts)
        old = documents.get(selection.mechanism_id)
        documents[selection.mechanism_id] = old if old == fresh else fresh
    active = {item.mechanism_id for item in profile.mechanisms if item.enabled}
    for name, (owner, surface) in surfaces.items():
        if surface.binding == 'artifact' and owner not in active:
            documents.pop(name, None)
            continue
        parameters = None
        if surface.binding == 'configuration':
            parameters = dict(getattr(profile, surface.key))
        elif surface.binding == 'settings':
            parameters = profile.component_settings.get(surface.key)
            if parameters is not None and name in profile.artifact_bindings:
                parameters = surface.restore(parameters or {}, read(profile.artifact_bindings[name]))
        else:
            reference = profile.prompt if surface.binding == 'prompt' else profile.artifact_bindings.get(surface.key)
            if reference and reference.startswith('sha256:'):
                parameters = surface.decode(read(reference))
            elif reference and surface.binding == 'prompt':
                from fruitfly_agent.lab.base_prompt import get_builtin
                parameters = surface.decode(get_builtin(reference).text)
            elif surface.default is not None and owner in active:
                parameters = surface.default()
        if parameters is not None:
            old = documents.get(name)
            fresh = ComponentConfiguration(name, surface.role, name, parameters,
                artifacts=(old.artifacts if old and surface.binding == 'artifact' else {}))
            # Keep authored references only when the values actually agree.
            if old and surface.normalize(dict(old.parameters)) == surface.normalize(dict(parameters)):
                fresh = old
            documents[name] = fresh
    roles.update({'executor': profile.model_profile} if profile.model_profile else {})
    return replace(profile, component_documents=tuple(documents.values()), model_roles=roles)


def bind_component_changes(profile, bindings):
    """Apply registered publication values to a new profile without writing sources."""
    from fruitfly_agent.runtime_spec import apply_profile_binding
    result = profile
    for binding in bindings:
        reference = 'sha256:' + hashlib.sha256(binding.text.encode('utf-8')).hexdigest()
        contents = {**result.artifact_contents, reference: binding.text}
        if binding.kind == 'configuration':
            result = apply_profile_binding(result, binding.kind, binding.key, binding.text)
        elif binding.kind == 'prompt':
            result = replace(result, prompt=reference)
        elif binding.kind == 'artifact':
            result = replace(result, artifact_bindings={**result.artifact_bindings, binding.key: reference})
        else:
            raise ValueError('unsupported component binding')
        result = replace(result, artifact_contents=contents)
    return result


def restore_component_settings(settings, artifact_key, text, catalog):
    """Update an existing settings surface through its registered artifact reader."""
    result = dict(settings)
    for _, surface in configuration_surfaces(catalog).values():
        if surface.binding == 'settings' and surface.id == artifact_key and surface.key in result:
            result[surface.key] = surface.normalize(surface.restore(result[surface.key], text))
    return result


def configuration_resources(profile, catalog, workspace):
    """Capture only explicit owner-declared state; never discover unrelated files."""
    files = {}
    for item in catalog.resolve(profile.mechanisms):
        capture = item.definition.configuration_snapshot
        if capture is not None:
            for entry in capture(item.parameters, Path(workspace).resolve()).files:
                if entry.path in files and entry != files[entry.path]:
                    raise ValueError('configuration resources disagree: ' + entry.path)
                files[entry.path] = entry
    return tuple(files[key] for key in sorted(files))


def materialize_system(profile, destination, *, catalog=None, artifact_reader=None, model_source=None,
                       resources=()):
    """Write an isolated complete system bundle; never change source documents."""
    if catalog is None:
        from .builtins import builtin_catalog
        catalog = builtin_catalog()
    import yaml
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    projected = component_profile(profile, catalog, artifact_reader=artifact_reader)
    configure_profile(replace(projected, configured=False), catalog)
    if model_source is not None:
        model_path = destination.parent / 'models.yaml'
        data = Path(model_source).read_bytes()
        if model_path.exists() and model_path.read_bytes() != data:
            raise ValueError('candidate model catalog conflicts with frozen source')
        if not model_path.exists():
            with model_path.open('xb') as stream:
                stream.write(data)
        projected = replace(projected, model_catalog='models.yaml')
    data = {'default_profile': profile.profile_id,
            'profiles': {profile.profile_id: projected.to_dict(references=False)}}
    with destination.open('x', encoding='utf-8') as stream:
        yaml.safe_dump(data, stream, allow_unicode=True, sort_keys=False)
    snapshot = {'schema_version': 1, 'profile': profile.profile_id,
        'semantic_identity': projected.profile_hash,
        'sources': [{'path': source.path, 'sha256': source.digest} for source in profile.source_files],
        'implementations': {item.definition.descriptor.mechanism_id: item.definition.implementation_id
                            for item in catalog.resolve(projected.mechanisms)},
        'config_sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
        'components': [{'id': d.id, 'role': d.role, 'implementation': d.implementation,
                        'content_sha256': hashlib.sha256(json.dumps(d.to_dict(), sort_keys=True,
                            separators=(',', ':'), allow_nan=False).encode()).hexdigest()}
                       for d in projected.component_documents]}
    snapshot['resources'] = []
    for entry in resources:
        relative = Path(entry.path)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('configuration resource must be workspace-relative')
        target = destination.parent / 'resources' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x', encoding='utf-8') as stream:
            stream.write(entry.content)
        snapshot['resources'].append({'path': 'resources/' + relative.as_posix(),
            'workspace_path': relative.as_posix(), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    if resources:
        snapshot['working_directory'] = 'resources'
    if model_source is not None:
        snapshot['model_catalog_sha256'] = hashlib.sha256((destination.parent / 'models.yaml').read_bytes()).hexdigest()
    with (destination.parent / 'snapshot.json').open('x', encoding='utf-8') as stream:
        json.dump(snapshot, stream, indent=2, ensure_ascii=False)
    return destination
