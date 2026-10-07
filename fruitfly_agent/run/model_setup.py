"""Stage model additions and credentials; persist with the harness save."""

from dataclasses import replace
import os
from pathlib import Path
import tempfile
import textwrap

import yaml

from fruitfly_agent.interactive.configuration import ConfigurationActionResult, ConfigurationParameter
from fruitfly_agent.interactive.model_setup import ModelSetupOption
from fruitfly_agent.providers.model_setup import CAPABILITY_OPTIONS, SERVICES, model_entry
from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.workspace import WorkspacePaths
from fruitfly_agent.providers.registry import load_model_specs
from fruitfly_agent.providers.specs import ModelCapabilities, ModelSpec

from .model_selection import model_catalog_path


class RunModelSetup:
    def __init__(self, controller, workspace: Path, environment: dict[str, str]) -> None:
        self.controller = controller
        self.workspace = workspace.resolve()
        self.environment = environment
        self.entries: dict[Path, dict[str, dict]] = {}
        self._secrets: dict[str, str] = {}

    def options(self) -> tuple[ModelSetupOption, ...]:
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
        descriptions = (
            "OpenAI account and API key. Uses the official address by default.",
            "Anthropic account and API key. Uses the official address by default.",
            "Gateway or self-hosted server supporting Responses API. Requires your service's API address and key.",
            "Gateway or self-hosted server supporting Messages API. Requires your service's API address and key.",
        )
        return tuple(ModelSetupOption(item[0], item[1], description,
                     (ConfigurationParameter("provider", "provider", "Selected API protocol adapter", "constant", item[2]),) + tuple(
            replace(field, description=(
                "Required: enter your service's base URL for this API protocol, not a chat webpage."
                if item[3] else "Optional: press Enter to use the official service's API address."
            )) if field.name == "base_url" else field for field in fields))
                     for item, description in zip(SERVICES, descriptions))

    def models(self, profile) -> dict[str, ModelSpec]:
        path = model_catalog_path(profile, self.controller._path)
        result = load_model_specs(path) if path.is_file() else {}
        result.update({name: ModelSpec.from_dict(name, raw) for name, raw in self.entries.get(path, {}).items()})
        return result

    def stage(self, option_id, values, secret) -> ConfigurationActionResult:
        name, entry = model_entry(option_id, values)
        profile = self.controller._draft.select(self.controller._selected)
        path = model_catalog_path(profile, self.controller._path)
        if not path.is_relative_to(self.workspace):
            raise ValueError("Model catalog is outside this workspace; configure a workspace-local catalog first")
        if name in self.models(profile):
            raise ValueError("Model label already exists; choose a different label")
        self._check_secret(entry["api_key_env"], secret)
        # Validate insertion before staging any changes, preserving existing text.
        _append_models(path.read_text(encoding="utf-8") if path.is_file() else "", {name: entry})
        self.entries.setdefault(path, {})[name] = entry
        if secret:
            self._secrets[entry["api_key_env"]] = secret
        self.controller._replace_profile(replace(profile, model_profile=name))
        return ConfigurationActionResult("Model and credential staged; save to use in a new session", changed=True)

    def credential_status(self, model_profile: str) -> str:
        profile = self.controller._draft.select(self.controller._selected)
        spec = self.models(profile)[model_profile]
        key = spec.provider.api_key_env
        return "API key set" if self._secrets.get(key) or self.environment.get(key) else "API key missing"

    def stage_credential(self, model_profile, secret) -> ConfigurationActionResult:
        profile = self.controller._draft.select(self.controller._selected)
        key = self.models(profile)[model_profile].provider.api_key_env
        self._check_secret(key, secret)
        if secret:
            self._secrets[key] = secret
        return ConfigurationActionResult("Credential staged; save to use in a new session", changed=True)

    def _check_secret(self, key, secret):
        if secret and (secret != secret.strip() or any(ord(char) < 33 for char in secret)):
            raise ValueError("API key must contain no whitespace or control characters")
        if not secret and not (self._secrets.get(key) or self.environment.get(key)):
            raise ValueError("API key is missing; enter a key or name an existing key variable")
        if secret and self.environment.get(key) and self.environment[key] != secret:
            raise ValueError("Key variable is already set; use a different variable or keep its existing value")
        if secret and self._secrets.get(key) and self._secrets[key] != secret:
            raise ValueError("Key variable already has another staged value")

    @property
    def changed(self) -> bool:
        return bool(self.entries or self._secrets)

    def reset(self) -> None:
        self.entries.clear()
        self._secrets.clear()

    def persist(self, save_harness) -> None:
        payloads = {}
        for path, entries in self.entries.items():
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            payloads[path] = _append_models(text, entries)
        env_path = WorkspacePaths(self.workspace).secret_file()
        if self._secrets:
            if env_path.is_symlink():
                raise ValueError("Refusing to write credentials through a symlink")
            text = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
            existing = load_env(env_path)
            if any(existing.get(key) and existing[key] != value for key, value in self._secrets.items()):
                raise ValueError("Credential file already has a different value; reload or choose another key variable")
            names = self._secrets.keys()
            lines = [line for line in text.splitlines(keepends=True) if line.strip().partition("=")[0].strip() not in names]
            prefix = "".join(lines)
            payloads[env_path] = prefix + ("\n" if prefix and not prefix.endswith("\n") else "") + "".join(f"{key}={value}\n" for key, value in self._secrets.items())
        originals = {path: path.read_bytes() if path.is_file() else None for path in payloads}
        written = []
        try:
            for path, text in payloads.items():
                _write(path, text.encode("utf-8"))
                written.append(path)
            save_harness()
        except BaseException:
            for path in reversed(written):
                original = originals[path]
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    _write(path, original)
            raise
        self.environment.update(self._secrets)
        self.reset()


def _append_models(text: str, entries: dict) -> str:
    if not text.strip():
        return yaml.safe_dump({"models": entries}, sort_keys=False, allow_unicode=True)
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


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
