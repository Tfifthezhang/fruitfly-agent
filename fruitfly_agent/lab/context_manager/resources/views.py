"""Deterministic navigation to public messages; no generated facts or extra model."""
import json


def history_view(history, path):
    if history.session is not None:
        history.bind(history.session.context_items())
    if path == 'index':
        return json.dumps({'messages': [
            {'reference': history.resource_prefix + 'messages/' + str(key), 'excerpt': value[:240]}
            for key, value in history.sources.items()]}, ensure_ascii=False, indent=2).encode()
    if path.startswith('messages/'):
        return history.sources[path.removeprefix('messages/')].encode()
    if path.startswith('artifacts/'):
        return history.text('sha256:' + path.removeprefix('artifacts/')).encode()
    raise ValueError('unknown history resource')
