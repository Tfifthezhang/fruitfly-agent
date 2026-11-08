"""Shared default optimization admission and inspectable field-level scope."""
from .components import resolve_harness
from .configuration import configuration_inventory, edit_grants, validate_component_options


def select_default_components(components, *, roles=None, capabilities=None):
    """Consume owner metadata; callers supply the applicable execution constraints."""
    return tuple(name for name, spec in components.items() if spec.default_selected
        and (roles is None or spec.role in roles)
        and (capabilities is None or not spec.required_capabilities - capabilities))


def optimization_grants(profile, catalog, component_ids=None):
    """Expand owner-admitted fields, including conditional/protected-field checks."""
    inventory = resolve_harness(profile, catalog)
    declarations = {c.component_id: c for c in inventory.components}
    selected = select_default_components(declarations) if component_ids is None else tuple(component_ids)
    rows = {r['id']: r for r in configuration_inventory(profile, catalog)}
    result = {}
    for name in selected:
        if name not in declarations or name not in rows or not rows[name]['enabled']:
            raise ValueError('optimization component is unavailable: ' + name)
        fields = []
        for path in rows[name]['fields']:
            try:
                options = edit_grants(profile, {name: {'fields': [path]}}, catalog)
                validate_component_options(catalog, name, options.get(name, {}), inventory)
            except ValueError:
                continue  # This exact field is protected or inactive in the current mode.
            fields.append(path)
        if not fields:
            raise ValueError('component declares no admitted optimization fields: ' + name)
        result.update(edit_grants(profile, {name: {'fields': fields}}, catalog))
    return result


def optimization_table(profile, catalog, selected, options, *, roles=None, capabilities=None):
    """Describe both enabled defaults and explicit exclusions before generation."""
    inventory = resolve_harness(profile, catalog)
    rows = {r['id']: r for r in configuration_inventory(profile, catalog)}
    table = []
    for spec in inventory.components:
        name = spec.component_id
        chosen = name in selected
        supported = ((roles is None or spec.role in roles) and
            (capabilities is None or not spec.required_capabilities - capabilities))
        reason = ('selected' if chosen else 'excluded by default' if not spec.default_selected
                  else 'unsupported by execution' if not supported else 'outside selected scope')
        grant = options.get(name, {})
        table.append({'component_id': name, 'role': spec.role, 'default_selected': spec.default_selected,
            'selected': chosen, 'reason': reason, 'required_capabilities': sorted(spec.required_capabilities),
            'editable_fields': list(grant.get('editable_fields', ())), 'bounds': grant.get('bounds', {}),
            'current_values': {path: value['effective'] for path, value in rows.get(name, {}).get('fields', {}).items()
                if path in grant.get('editable_fields', ())}})
    return table


def render_optimization_table(rows):
    lines = ['# Candidate generation configuration', '',
        '| Component | Role | Default | Selected | Editable fields | Reason |',
        '|---|---|---|---|---|---|']
    for row in rows:
        lines.append('| ' + ' | '.join((row['component_id'], row['role'], str(row['default_selected']),
            str(row['selected']), ', '.join(row['editable_fields']), row['reason'])) + ' |')
    return '\n'.join(lines) + '\n'


def registry_optimization_table(registry, selected):
    """Use assembled owner descriptions for embedding jobs without a profile loader."""
    descriptions = registry.descriptions(selected)
    rows = []
    for name, adapter in registry.adapters.items():
        fields = descriptions.get(name, {}).get('fields', [])
        grant = registry.options.get(name, {})
        paths = grant.get('editable_fields', [f['path'] for f in fields])
        rows.append({'component_id': name, 'role': adapter.snapshot().role,
            'default_selected': adapter.optimization.default_selected, 'selected': name in selected,
            'reason': 'selected' if name in selected else 'excluded by default' if not adapter.optimization.default_selected else 'outside material or explicit scope',
            'editable_fields': list(paths), 'bounds': grant.get('bounds', {}),
            'required_capabilities': sorted(adapter.optimization.required_capabilities),
            'current_values': {f['path']: f['current'] for f in fields if f['path'] in paths}})
    return rows
