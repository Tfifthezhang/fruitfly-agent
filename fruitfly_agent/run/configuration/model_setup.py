"""Stage model additions and credentials; persist with the harness save."""

from dataclasses import replace
from pathlib import Path
import json
import textwrap

import yaml

from fruitfly_agent.interactive.contracts.configuration import ConfigurationActionResult, ConfigurationParameter
from fruitfly_agent.interactive.contracts.model_setup import ModelSetupOption
from fruitfly_agent.providers.model_setup import (CAPABILITY_OPTIONS, SERVICES, model_entry, setup_defaults,
    setup_selection, setup_initial, setup_service, default_parameters)
from fruitfly_agent.providers.registry import load_model_specs, ProviderRegistry, default_registry
from fruitfly_agent.providers.services import service_definition
from fruitfly_agent.providers.specs import ModelCapabilities, ModelSpec, ordered_model_entry

from .resolution import model_catalog_path
from .persistence import write_bytes
from .credentials import CredentialDraft
from .model_catalog import order_model_catalog


class RunModelSetup:
    def __init__(self, *, config_path: Path, current_profile, stage_profile,
                 workspace: Path, environment: dict[str, str], credentials: CredentialDraft | None = None,
                 registry: ProviderRegistry | None = None) -> None:
        self.config_path = config_path
        self.current_profile = current_profile
        self.stage_profile = stage_profile
        self.workspace = workspace.resolve()
        self.environment = environment
        self.entries: dict[Path, dict[str, dict]] = {}
        self.credentials = credentials or CredentialDraft(self.workspace, environment)
        self.registry = registry or default_registry()

    def _fields(self) -> tuple[ConfigurationParameter, ...]:
        fields = (
            ConfigurationParameter("profile", "models.<name>", "A name for this model in menus, such as work-model. This is not the model ID.", "text", "my-model"),
            ConfigurationParameter("model", "model", "Copy the exact model ID from your service's documentation or model list.", "text", ""),
            ConfigurationParameter("base_url", "base_url", "Blank uses the official endpoint; required for custom services", "text", ""),
            ConfigurationParameter("context_window", "context_window", "Token limit documented by your service", "text", ""),
            ConfigurationParameter("max_output_tokens", "max_output_tokens", "Smaller than the context window; leave room for input", "text", ""),
            ConfigurationParameter("api_key_env", "api_key_env", "Optional: blank creates a variable for this model; enter a variable name to reuse a key", "text", ""),
        )
        defaults = ModelCapabilities()
        fields += tuple(ConfigurationParameter(f"capabilities.{name}", name, description, "bool",
            getattr(defaults, name), choices=(True,) if required else (False, True))
            for name, description, required in CAPABILITY_OPTIONS)
        return fields + (ConfigurationParameter('parameters', 'parameters',
            'Edit the complete API options as one JSON object. Reasoning effort defaults to medium; '
            'use {} for server defaults. Confirm parameter support with your model service.', 'json', ''),)

    def options(self) -> tuple[ModelSetupOption, ...]:
        return tuple(ModelSetupOption(item.id, item.label, item.description,
            (self.field(item.id, 'protocol', {}),
             ConfigurationParameter('sdk', 'sdk', 'Automatically selected client library', 'constant', '')) + self._fields(),
            group=item.label) for item in SERVICES
            if setup_selection(item.id, {}, self.registry.registered_pairs())[1])

    def field(self, option_id, name, values) -> ConfigurationParameter:
        protocol, choices = setup_selection(option_id, values, self.registry.registered_pairs())
        selected = setup_service(option_id)
        if name == 'protocol':
            details = []
            for choice in choices:
                definition = service_definition(selected.service, choice)
                details.append(f'{choice}: {definition.base_url or "your API base URL"}. {definition.description}')
            return ConfigurationParameter(name, name, 'Some models may not support the selected protocol. Confirm support with your service.\n' +
                '\n'.join(details), 'choice', protocol, choices=choices)
        if name == 'sdk':
            return ConfigurationParameter(name, name, 'Automatically selected from registered adapters',
                'constant', self.registry.sdk_for(protocol))
        field = next((item for item in self._fields() if item.name == name), None)
        if field is None:
            raise ValueError('unsupported model setup field: ' + name)
        if name == 'parameters':
            return replace(field, value=json.dumps(default_parameters(protocol), ensure_ascii=False))
        initial = setup_initial(option_id, protocol)
        description = ('Enter the API base URL for this protocol; confirm region and account access.'
                       if name == 'base_url' else field.description)
        return replace(field, value=initial.get(name, field.value), description=description)

    def defaults(self, option_id, values) -> dict:
        return setup_defaults(option_id, values)

    def models(self, profile) -> dict[str, ModelSpec]:
        path = model_catalog_path(profile, self.config_path)
        result = load_model_specs(path) if path.is_file() else {}
        result.update({name: ModelSpec.from_dict(name, raw) for name, raw in self.entries.get(path, {}).items()})
        return result

    def stage(self, option_id, values, secret) -> ConfigurationActionResult:
        name, entry = model_entry(option_id, values, registry=self.registry)
        self.registry.validate(ModelSpec.from_dict(name, entry))
        profile = self.current_profile()
        path = model_catalog_path(profile, self.config_path)
        if not path.is_relative_to(self.workspace):
            raise ValueError("Model catalog is outside this workspace; configure a workspace-local catalog first")
        if name in self.models(profile):
            raise ValueError("Model label already exists; choose a different label")
        self._check_secret(entry["api_key_env"], secret)
        # Validate insertion before staging any changes, preserving existing text.
        _append_models(path.read_text(encoding="utf-8") if path.is_file() else "", {name: entry})
        self.entries.setdefault(path, {})[name] = entry
        if secret:
            self.credentials.values[entry["api_key_env"]] = secret
        self.stage_profile(replace(profile, model_profile=name))
        return ConfigurationActionResult("Model and credential staged; save before applying settings", changed=True)

    def credential_status(self, model_profile: str) -> str:
        profile = self.current_profile()
        spec = self.models(profile)[model_profile]
        key = spec.provider.api_key_env
        return "API key set" if self.credentials.values.get(key) or self.environment.get(key) else "API key missing"

    def stage_credential(self, model_profile, secret) -> ConfigurationActionResult:
        profile = self.current_profile()
        key = self.models(profile)[model_profile].provider.api_key_env
        self._check_secret(key, secret)
        if secret:
            self.credentials.values[key] = secret
        return ConfigurationActionResult("Credential staged; save before applying settings", changed=True)

    def _check_secret(self, key, secret):
        if secret and (secret != secret.strip() or any(ord(char) < 33 for char in secret)):
            raise ValueError("API key must contain no whitespace or control characters")
        if not secret and not (self.credentials.values.get(key) or self.environment.get(key)):
            raise ValueError("API key is missing; enter a key or name an existing key variable")
        self.credentials.check(key, secret)

    @property
    def changed(self) -> bool:
        return bool(self.entries or self.credentials.values)

    def reset(self) -> None:
        self.entries.clear()
        self.credentials.values.clear()

    def payloads(self) -> dict[Path, str]:
        """Prepare file contents without publishing models or credentials."""
        payloads = {}
        for path, entries in self.entries.items():
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            payloads[path] = _append_models(text, entries)
        payloads.update(self.credentials.payloads())
        return payloads

    def persist(self, save_harness) -> None:
        payloads = self.payloads()
        originals = {path: path.read_bytes() if path.is_file() else None for path in payloads}
        written = []
        try:
            for path, text in payloads.items():
                write_bytes(path, text.encode("utf-8"))
                written.append(path)
            save_harness()
        except BaseException:
            for path in reversed(written):
                original = originals[path]
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    write_bytes(path, original)
            raise
        self.environment.update(self.credentials.values)
        self.reset()


def _append_models(text: str, entries: dict) -> str:
    entries = {name: ordered_model_entry(raw) for name, raw in entries.items()}
    if not text.strip():
        return yaml.safe_dump({"models": entries}, sort_keys=False, allow_unicode=True)
    text = order_model_catalog(text)
    root = yaml.compose(text)
    if not isinstance(root, yaml.MappingNode):
        raise ValueError("Model catalog must be a YAML mapping")
    node = next((value for key, value in root.value if key.value == "models"), None)
    if not isinstance(node, yaml.MappingNode) or node.flow_style:
        raise ValueError("Model wizard requires a block-style models mapping; edit this catalog manually")
    existing = {key.value for key, value in node.value}
    if existing & entries.keys():
        raise ValueError("Model catalog changed or label already exists; choose a different label")
    addition = textwrap.indent(yaml.safe_dump(entries, sort_keys=False, allow_unicode=True), " " * (node.start_mark.column))
    index = node.end_mark.index
    prefix = text[:index]
    result = prefix + ("\n" if prefix and not prefix.endswith("\n") else "") + addition + text[index:]
    parsed = yaml.safe_load(result)
    if any(parsed["models"].get(name) != value for name, value in entries.items()):
        raise ValueError("Cannot safely append to this catalog; edit it manually")
    return result


