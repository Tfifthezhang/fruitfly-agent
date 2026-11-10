"""Resolve stage-local edit grants through their registered owners."""
from fruitfly_agent.lab.catalog import optimization_grants, edit_grants


def resolve_optimization(document, profile, catalog):
    from fruitfly_agent.runtime_spec.documents import mapping
    settings = mapping(document.settings('propose').get('optimization', {}), {'scope', 'include', 'exclude'}, 'optimization')
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
