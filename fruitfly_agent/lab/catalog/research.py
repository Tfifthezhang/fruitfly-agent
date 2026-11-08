"""Prepare complete owner-admitted component snapshots without task environments."""
from types import SimpleNamespace
from .configuration import configuration_surfaces
from .adapters.parameters import ParameterTarget
from .defaults import read_default
from .optimization import optimization_grants


def configuration_targets(profile, catalog, component_options, *, config, artifact_reader, workspace):
    surfaces = configuration_surfaces(catalog)
    enabled = {r.definition.descriptor.mechanism_id: r for r in catalog.resolve(profile.mechanisms)}
    state = SimpleNamespace(config=config)
    context = SimpleNamespace(workspace=workspace, artifact_reader=artifact_reader,
        artifact_bindings=profile.artifact_bindings, component_settings=profile.component_settings)
    targets = []
    # Freeze all public surface and parameter owners. Grants only narrow writes;
    # they never truncate the candidate's execution configuration.
    for name, (owner, surface) in surfaces.items():
        if surface.target_factory is None or (owner not in enabled and not surface.standalone):
            continue
        parameters = profile.component_settings.get(surface.key)
        if parameters is None:
            document, _ = read_default(catalog, name)
            parameters = dict(document.parameters)
        if surface.binding == 'prompt':
            parameters = {'instructions': {'system': config.system_prompt}}
        reference = profile.artifact_bindings.get(name)
        if reference:
            parameters = surface.restore(parameters, artifact_reader(reference))
        context.model_parameters = enabled[owner].parameters if owner in enabled else {}
        context.component_id = owner
        target = surface.target_factory(state, context, surface.normalize(parameters))
        targets.append(target)
    for name, row in enabled.items():
        if name in surfaces or not row.definition.parameter_paths:
            continue
        # Component specs identify the mechanisms which actually own parameters.
        specs = row.definition.component_specs(row.parameters, True) if row.definition.component_specs else ()
        if not any(s.component_id == name for s in specs):
            continue
        mapping = {('parameters.' + path): key for key, path in row.definition.parameter_paths.items()}
        admitted = optimization_grants(profile, catalog, (name,))[name]['editable_fields']
        options = component_options.get(name, {})
        selected = options.get('editable_fields', admitted)
        if set(selected) - set(admitted):
            raise ValueError('research needs owner-admitted parameter fields: ' + name)
        spec = next(s for s in specs if s.component_id == name)
        targets.append(ParameterTarget(row.definition, row.parameters, {mapping[p] for p in selected},
            default_selected=spec.default_selected, required_capabilities=spec.required_capabilities))
    available = {t.snapshot().target_id: t for t in targets}
    for name, options in component_options.items():
        if name not in available:
            raise ValueError('research target requires an owner-supplied resource factory: ' + name)
        available[name].validate_options(options)
    return tuple(targets)
