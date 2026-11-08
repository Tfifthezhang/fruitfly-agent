"""Immutable identities for injected stage extensions."""
from fruitfly_agent.improvement.contracts.versions import canonical_json

def extension_spec(extension):
    if extension is None:
        return None
    configuration = getattr(extension, 'configuration', None)
    if not isinstance(configuration, dict):
        raise ValueError('workflow extensions require an explicit configuration identity')
    value = {'implementation': getattr(extension, 'implementation_id',
        getattr(extension, '__module__', type(extension).__module__) + '.' +
        getattr(extension, '__qualname__', type(extension).__qualname__)), 'configuration': configuration}
    # Return detached JSON so subsequent plugin mutation cannot rewrite a preview.
    import json
    return json.loads(canonical_json(value))

