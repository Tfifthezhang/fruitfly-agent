"""Separate authored API and subscription catalogs without copying credentials."""
import yaml
from .model_catalog import _content_end

def separate_models(text: str) -> tuple[str, str | None]:
    if not text.strip():
        return text, None
    root = yaml.compose(text)
    if not isinstance(root, yaml.MappingNode):
        raise ValueError('Model catalog must be a mapping')
    models = next((v for k, v in root.value if k.value == 'models'), None)
    connections = next(((k, v) for k, v in root.value if k.value == 'connections'), None)
    raw = yaml.safe_load(text)
    connected = {name for name, value in raw.get('models', {}).items() if 'connection' in value or 'access' in value}
    if not connected and connections is None:
        return text, None
    if not isinstance(models, yaml.MappingNode) or models.flow_style:
        raise ValueError('Expand model catalogs to block mappings before separating subscriptions')
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    patches = []
    moved = []
    def line_end(index: int) -> int:
        if index and text[index - 1] == '\n':
            return index
        end = text.find('\n', index)
        return len(text) if end < 0 else end + 1

    for key, value in models.value:
        if key.value not in connected:
            continue
        start = offsets[key.start_mark.line]
        end = line_end(_content_end(value))
        moved.append(text[start:end])
        patches.append((start, end, ''))
    connection_text = ''
    if connections is not None:
        key, value = connections
        start = offsets[key.start_mark.line]
        end = line_end(_content_end(value))
        connection_text = text[start:end]
        patches.append((start, end, ''))
    api = text
    for start, end, replacement in sorted(patches, reverse=True):
        api = api[:start] + replacement + api[end:]
    if len(connected) == len(models.value):
        header = next(k for k, v in root.value if v is models)
        colon = text.index(':', header.end_mark.index)
        api = api[:colon + 1] + ' {}' + api[colon + 1:]
    subscription = 'models:\n' + ''.join(moved) + ('\n' if moved and not moved[-1].endswith('\n') else '') + connection_text
    if not connected:
        subscription = 'models: {}\n' + connection_text
    expected_api = {**raw, 'models': {key: value for key, value in raw['models'].items() if key not in connected}}
    expected_api.pop('connections', None)
    if yaml.safe_load(api) != expected_api:
        raise ValueError('Cannot safely separate model catalogs')
    expected_subscription = {'models': {key: raw['models'][key] for key in connected}}
    if connections is not None:
        expected_subscription['connections'] = raw['connections']
    if yaml.safe_load(subscription) != expected_subscription:
        raise ValueError('Cannot safely separate subscription entries')
    return api, subscription
