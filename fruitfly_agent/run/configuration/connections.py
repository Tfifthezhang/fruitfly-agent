"""Project connection drafts and projection of account/model services."""
from __future__ import annotations
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import time
from typing import Any, Callable
import yaml
from fruitfly_agent.providers.connections.service import ConnectionService
from fruitfly_agent.providers.specs import ModelSpec
from fruitfly_agent.interactive.contracts.model_connections import ConnectionOption, ConnectionAccount, ModelChoice
from fruitfly_agent.interactive.contracts.configuration import ConfigurationActionResult
from .resolution import model_catalog_path

@dataclass(frozen=True)
class ModelConnectionDraft:
    config_path: Path
    workspace: Path
    environment: dict[str, str]
    entries: dict[Path, dict[str, dict]]
    current_profile: Callable
    stage_profile: Callable
    models: Callable
    capture: Callable
    validate: Callable
    select_store: Callable


class RunModelConnections:
    def __init__(self, draft: ModelConnectionDraft, service: ConnectionService):
        self.draft, self.service = draft, service
        self.pending: dict[Path, dict[str, dict[str, Any]]] = {}
        self.updates: dict[Path, dict[str, dict[str, Any]]] = {}
        self._attempts: dict[str, Any] = {}

    def options(self) -> tuple[ConnectionOption, ...]:
        return tuple(ConnectionOption(d.id, d.label, d.method.kind, d.method.label, d.method.url)
                     for d in self.service.registry.definitions())

    def definitions(self, *sources: Path) -> dict[str, dict[str, Any]]:
        values: dict[str, dict[str, Any]] = {}
        for source in dict.fromkeys(sources):
            raw = yaml.safe_load(source.read_text()) if source.is_file() else {}
            values.update((raw or {}).get('connections', {}))
            values.update(self.pending.get(source, {}))
        return values

    def accounts(self) -> tuple[ConnectionAccount, ...]:
        profile = self.draft.current_profile()
        bindings = self.definitions(*profile.model_sources(self.draft.config_path))
        return tuple(ConnectionAccount(row['account'], row['integration'], row['label'], row['status'],
            tuple(name for name, value in bindings.items() if value.get('account') == row['account']))
            for row in self.service.accounts())

    def open_browser(self, url: str) -> bool:
        import webbrowser
        return webbrowser.open(url)

    def choose_storage(self, backend: str) -> None:
        self.service.choose_storage(backend)
        self.draft.select_store(self.service.credentials())

    def connect_key(self, integration: str, key: str, label: str, account: str = '') -> str:
        return self.service.connect_key(integration, key, label, account)

    def use_key_variable(self, integration: str, name: str) -> str:
        return self.service.bind_variable(integration, name, self.draft.environment)

    def begin_login(self, integration: str, account: str = '') -> Any:
        from uuid import uuid4
        attempt, url, record = self.service.begin_login(integration, account)
        identity = uuid4().hex
        self._attempts[identity] = (attempt, record)
        return attempt, url, identity

    def complete_login(self, attempt: Any, identity: str) -> str:
        selected, record = self._attempts.pop(identity)
        if selected is not attempt:
            raise ValueError('Authorization attempt mismatch')
        return self.service.complete_login(attempt, record)

    def cancel_login(self, identity: str) -> None:
        value = self._attempts.pop(identity, None)
        if value is not None:
            value[0].close()

    def rename(self, account: str, label: str) -> ConfigurationActionResult:
        self.service.rename(account, label)
        return ConfigurationActionResult('Account renamed; model configuration unchanged.')

    def logout(self, account: str) -> bool:
        return self.service.logout(account)

    def refresh(self, integration: str, account: str) -> None:
        self.service.refresh(integration, account, force=True)

    def catalog_status(self, integration: str, account: str) -> str:
        snapshot = self.service.snapshot(integration, account)
        status = self.service.state(integration, account)
        if snapshot is None:
            return status or 'No cached directory. Refresh models to connect.'
        age = max(0, int(time.time() - snapshot.fetched_at))
        return f'Cached directory · updated {age // 3600}h ago. Availability is checked by the service.' + ('\n' + status if status else '')

    def _preferences(self) -> dict[str, Any]:
        path = self.service.cache.directory / 'preferences.json'
        try:
            raw = json.loads(path.read_text())
            return raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            return {}

    def _remember(self, integration: str, account: str, model: str, *, favorite: bool = False) -> None:
        from .persistence import write_bytes
        key = self.service.scope(integration, account).key()
        preferences = self._preferences()
        values = preferences.setdefault(key, {'recent': [], 'favorites': []})
        field = 'favorites' if favorite else 'recent'
        previous = values.get(field, [])
        values[field] = ([v for v in previous if v != model] if favorite and model in previous
                         else [model, *[v for v in previous if v != model]])[:100]
        path = self.service.cache.directory / 'preferences.json'
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_bytes(path, json.dumps(preferences).encode())

    def toggle_favorite(self, integration: str, account: str, model: str) -> None:
        self._remember(integration, account, model, favorite=True)

    def models(self, integration: str, account: str, query: str = '') -> tuple[ModelChoice, ...]:
        snapshot = self.service.snapshot(integration, account, refresh_stale=True)
        if snapshot is None:
            return ()
        preferences = self._preferences().get(self.service.scope(integration, account).key(), {})
        rows = []
        for model in snapshot.models:
            if query.casefold() not in (str(model['id']) + ' ' + str(model.get('name', ''))).casefold():
                continue
            caps = model.get('capabilities', {})
            valid = caps.get('tools') is True and caps.get('streaming') is True
            rows.append(ModelChoice(model['id'], model.get('name', model['id']), model.get('context_window'),
                model.get('max_output_tokens'), valid, '' if valid else 'Tool calling or streaming is unconfirmed',
                model['id'] in preferences.get('favorites', []), model['id'] in preferences.get('recent', []),
                dict(caps), dict(model.get('pricing', {})),
                {key: tuple(choices) for key, choices in model.get('options', {}).items()}))
        return tuple(sorted(rows, key=lambda row: (not row.favorite, not row.recent)))

    def stage(self, integration: str, account: str, model: str, alias: str,
              context_window: int | None = None, output_limit: int | None = None, parameters: dict[str, str] | None = None) -> ConfigurationActionResult:
        import re
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', alias):
            raise ValueError('Model label must use 1–80 letters, digits, dots, underscores or hyphens')
        if not self.service.ready(integration, account):
            raise ValueError('Connect an account with model usage permission first')
        snapshot = self.service.snapshot(integration, account)
        row = next((r for r in snapshot.models if r['id'] == model), None) if snapshot else None
        if row is None:
            raise ValueError('Model is not in the cached directory; refresh and select again')
        if parameters is not None and any(value not in row.get('options', {}).get(key, ())
                                          for key, value in parameters.items()):
            raise ValueError('Model directory does not confirm the selected request option')
        caps = row.get('capabilities', {})
        if not caps.get('tools') or not caps.get('streaming'):
            raise ValueError('Model requires confirmed tool calling and streaming support')
        context = context_window or row.get('context_window')
        output = output_limit or row.get('max_output_tokens')
        definition = self.service.registry.get(integration)
        known_max = row.get('max_output_tokens')
        if not definition.output_enforced and type(known_max) is int and type(output) is int and output < known_max:
            raise ValueError('This connection cannot enforce a smaller output limit; reserve the documented model maximum')
        if type(context) is not int or type(output) is not int or not 0 < output < context:
            raise ValueError('Confirm documented context and maximum output limits before saving')
        if type(row.get('input_limit')) is int:
            context = min(context, row['input_limit'] + output)
        profile = self.draft.current_profile()
        primary = model_catalog_path(profile, self.draft.config_path)
        sources = profile.model_sources(self.draft.config_path)
        companion = sources[1] if len(sources) > 1 else primary.with_name('subscriptions.yaml')
        if len(sources) == 1 and companion.exists():
            raise ValueError('Declare the existing subscriptions catalog in models.subscriptions before editing it')
        path = companion
        if primary.is_file() and not companion.is_file():
            from .model_files import separate_models
            if separate_models(primary.read_text())[1] is not None:
                path = primary
        if any(not source.is_relative_to(self.draft.workspace) for source in (primary, companion)):
            raise ValueError('Model catalog must be inside the workspace')
        connection = self.service.profile(integration, account)
        existing = self.draft.models(profile).get(alias)
        if existing and (existing.access != connection.to_dict() or existing.model != model):
            raise ValueError('Model label already exists; use a different label')
        connections = self.definitions(primary, companion)
        name = next((name for name, value in connections.items()
                     if value == connection.to_dict()), None)
        new_connection = name is None
        if name is None:
            name = integration + '-' + account[:12]
            if name in connections:
                raise ValueError('Connection label already exists')
        entry = {'connection': name, 'model': model, 'context_window': context,
            'max_output_tokens': output, 'capabilities': {k: v for k, v in caps.items() if k != 'parallel_tool_calls'}}
        if parameters:
            entry['parameters'] = parameters
        changes = {}
        if existing and path.is_file():
            authored = yaml.safe_load(path.read_text()).get('models', {}).get(alias)
            if authored is not None:
                changes = {key: entry[key] for key in ('context_window', 'max_output_tokens', 'capabilities')}
                previous_parallel = authored.get('capabilities', {}).get('parallel_tool_calls')
                if previous_parallel is not None:
                    changes['capabilities']['parallel_tool_calls'] = previous_parallel
                if parameters is not None:
                    previous_options = authored.get('parameters', {})
                    changes['parameters'] = {
                        **{key: value for key, value in previous_options.items() if key not in row.get('options', {})},
                        **parameters,
                    }
                entry = {**authored, **changes}
        self.draft.validate(ModelSpec.from_dict(alias, self.service.registry.resolve(
            connection, {key: value for key, value in entry.items() if key != 'connection'})))
        self.draft.capture(primary)
        self.draft.capture(companion)
        if new_connection:
            self.pending.setdefault(path, {})[name] = connection.to_dict()
        if changes:
            self.updates.setdefault(path, {})[alias] = changes
        self.draft.entries.setdefault(path, {})[alias] = entry
        self.draft.stage_profile(replace(profile, model_profile=alias,
            subscription_catalog=profile.subscription_catalog or os.path.relpath(companion, self.draft.config_path.parent)))
        self._remember(integration, account, model)
        return ConfigurationActionResult('Model staged; save and apply to use it.', changed=True)

    def parameters(self, alias: str) -> dict[str, Any]:
        return dict(self.draft.models(self.draft.current_profile())[alias].parameters)

    def edit_parameters(self, alias: str, parameters: dict[str, Any]) -> ConfigurationActionResult:
        profile = self.draft.current_profile()
        primary = model_catalog_path(profile, self.draft.config_path)
        spec = self.draft.models(profile)[alias]
        sources = profile.model_sources(self.draft.config_path)
        companion = sources[1] if len(sources) > 1 else None
        path = companion if companion is not None and spec.access and (alias in self.draft.entries.get(companion, {}) or
            companion.is_file() and alias in (yaml.safe_load(companion.read_text()) or {}).get('models', {})) else primary
        ModelSpec.from_dict(alias, {**spec.to_dict(), 'parameters': parameters})
        if path.is_file() and alias in yaml.safe_load(path.read_text())['models']:
            authored = yaml.safe_load(path.read_text())['models'][alias]
            self.updates.setdefault(path, {}).setdefault(alias, {})['parameters'] = parameters
        else:
            authored = self.draft.entries[path][alias]
        self.draft.capture(path)
        self.draft.entries.setdefault(path, {})[alias] = {**authored, 'parameters': parameters}
        return ConfigurationActionResult('Request options staged; save and apply to use them.', changed=True)

    def payload(self, path: Path, text: str) -> str:
        for name, changes in self.updates.get(path, {}).items():
            text = _patch_model(text, name, changes)
        entries = self.pending.get(path, {})
        if not entries:
            return text
        # Preserve unrelated authored catalog content.
        return _append_mapping(text, 'connections', entries)


def _append_mapping(text: str, key: str, entries: dict[str, Any]) -> str:
    import textwrap
    root = yaml.compose(text)
    if not isinstance(root, yaml.MappingNode):
        raise ValueError('Model catalog must be a mapping')
    node = next((v for k, v in root.value if k.value == key), None)
    original = yaml.safe_load(text)
    if node is None:
        return text + ('\n' if text and not text.endswith('\n') else '') + yaml.safe_dump({key: entries}, sort_keys=False)
    if not isinstance(node, yaml.MappingNode) or node.flow_style:
        raise ValueError('Expand connection mappings to block YAML before editing')
    existing = original[key]
    if existing.keys() & entries.keys():
        raise ValueError('Connection catalog changed; reload before saving')
    addition = textwrap.indent(yaml.safe_dump(entries, sort_keys=False), ' ' * node.start_mark.column)
    index = node.end_mark.index
    return text[:index] + ('\n' if index and text[index - 1] != '\n' else '') + addition + text[index:]


def _patch_model(text: str, alias: str, changes: dict[str, Any]) -> str:
    """Replace reviewed value nodes, preserving other authored fields and comments."""
    root = yaml.compose(text)
    models = next(v for k, v in root.value if k.value == 'models')
    entry = next(v for k, v in models.value if k.value == alias)
    patches = []
    for name, value in changes.items():
        node = next((v for k, v in entry.value if k.value == name), None)
        if node is None:
            if entry.flow_style:
                raise ValueError('Expand the model entry before adding ' + name)
            from .model_catalog import _content_end
            end = text.find('\n', _content_end(entry))
            if end < 0:
                end = len(text)
            encoded = yaml.safe_dump({name: value}, default_flow_style=False, sort_keys=False)
            import textwrap
            patches.append((end, end, '\n' + textwrap.indent(encoded.rstrip('\n'), ' ' * entry.start_mark.column), None))
            continue
        replacement = yaml.safe_dump(value, default_flow_style=True, sort_keys=False).split('\n...')[0].strip()
        patches.append((node.start_mark.index, node.end_mark.index, replacement, node.end_mark.column if node.end_mark.line > node.start_mark.line else None))
    for start, end, replacement, trailing_indent in sorted(patches, reverse=True):
        if trailing_indent is not None:
            replacement += '\n' + ' ' * trailing_indent
        text = text[:start] + replacement + text[end:]
    parsed = yaml.safe_load(text)
    if any(parsed['models'][alias][key] != value for key, value in changes.items()):
        raise ValueError('Cannot safely update model fields')
    return text
