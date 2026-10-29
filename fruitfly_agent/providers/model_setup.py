"""Offline validation and form descriptions for the supported API protocols."""

import re
import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit

from .specs import ModelCapabilities, ModelSpec, ordered_model_entry
from .request_options import validate_request_options
from .transport import TransportPolicy
from .services import builtin_services, service_definition
from .registry import ProviderRegistry, default_registry


CAPABILITY_OPTIONS = (
    ("tools", "Model tool calls; required by this harness", True),
    ("parallel_tool_calls", "Multiple tool calls in a single model response", False),
    ("vision", "Image input supported by the model and endpoint", False),
    ("reasoning", "Reasoning capability; this declaration does not enable or disable model thinking", False),
    ("streaming", "Streaming responses; required by this harness", True),
)


@dataclass(frozen=True)
class SetupService:
    id: str
    label: str
    protocol: str
    service: str
    description: str
    custom: bool = False
    initial: dict = field(default_factory=dict)


# Services and addresses have one owner; no model names or limits are inferred.
SERVICES = tuple(SetupService(
    'custom' if definition.id == 'generic' else definition.id,
    definition.label, definition.default_protocol, definition.id,
    'Choose a protocol, then enter the model ID and documented limits. Confirm endpoint and account access.',
    custom=definition.id == 'generic', initial={'api_key_env': definition.api_key_env},
) for definition in builtin_services())


def setup_service(option_id: str) -> SetupService:
    selected = next((item for item in SERVICES if item.id == option_id), None)
    if selected is None:
        raise ValueError('unsupported API service')
    return selected


def setup_selection(option_id: str, values, pairs: tuple[tuple[str, str], ...]) -> tuple[str, tuple[str, ...]]:
    selected = setup_service(option_id)
    definition = service_definition(selected.service, selected.protocol)
    registered = tuple(dict.fromkeys(protocol for _, protocol in pairs))
    order = ('responses', 'messages', 'chat-completions', *registered)
    choices = tuple(dict.fromkeys(protocol for protocol in order if protocol in registered
        and (selected.custom or protocol in definition.protocols)))
    value = values.get('protocol', selected.protocol)
    return value if value in choices else next(iter(choices), ''), choices


def setup_initial(option_id: str, protocol: str) -> dict:
    selected = setup_service(option_id)
    definition = service_definition(selected.service, protocol)
    return {**selected.initial, 'base_url': definition.base_url or ''}


def default_parameters(protocol: str) -> dict:
    """Editable protocol defaults, independent of vendor, model and capability flags."""
    defaults: dict[str, dict] = {
        'responses': {'reasoning': {'effort': 'medium'}},
        'messages': {'output_config': {'effort': 'medium'}},
        'chat-completions': {'reasoning_effort': 'medium'},
    }
    return deepcopy(defaults.get(protocol, {}))


def setup_defaults(option_id: str, values) -> dict:
    selected = setup_service(option_id)
    protocol = values.get('protocol', selected.protocol)
    parameters = default_parameters(protocol)
    if values.get('parameters', '') != '':
        try:
            parameters = json.loads(values['parameters'])
        except (TypeError, ValueError) as exc:
            raise ValueError('parameters must be a JSON object; use {} for server defaults') from exc
    parameters = validate_request_options(protocol, parameters)
    return {"service": selected.service, "parameters": parameters,
            "transport": {**asdict(TransportPolicy()), "retry_max": 3, "retry_base_delay": 1.0}}


def model_entry(option_id: str, values, *, registry: ProviderRegistry | None = None) -> tuple[str, dict]:
    service = setup_service(option_id)
    registry = registry or default_registry()
    protocol = values.get('protocol', service.protocol)
    _, choices = setup_selection(option_id, values, registry.registered_pairs())
    if protocol not in choices:
        raise ValueError('unavailable service/protocol combination: ' + service.service + '/' + protocol)
    sdk = registry.sdk_for(protocol)
    if 'sdk' in values and values['sdk'] != sdk:
        raise ValueError('SDK is automatic for this protocol; expected ' + sdk)
    initial = setup_initial(option_id, protocol)
    profile = values.get("profile", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", profile):
        raise ValueError("models.<name> must use 1–80 letters, digits, dots, underscores, or hyphens")
    model = values.get("model", "").strip()
    if not model or any(ord(char) < 32 for char in model):
        raise ValueError("model must be non-empty text")
    url = values.get("base_url", "").strip()
    url = url or str(initial.get("base_url", ""))
    if service.custom and not url:
        raise ValueError("Custom services require base_url (API base URL)")
    if url:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url (API base URL) must be HTTP(S), without credentials, query, or fragment")
    try:
        context = int(values.get("context_window", ""))
        output = int(values.get("max_output_tokens", ""))
    except ValueError:
        raise ValueError("context_window and max_output_tokens must be positive integers") from None
    if not 0 < output < context:
        raise ValueError("max_output_tokens must be positive and smaller than context_window")
    key_env = values.get("api_key_env", "").strip() or "FRUITFLY_MODEL_" + profile.upper().replace("-", "_").replace(".", "_") + "_API_KEY"
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_env):
        raise ValueError("api_key_env must be a valid environment variable name")
    defaults = ModelCapabilities()
    capabilities = {}
    for name, description, required in CAPABILITY_OPTIONS:
        value = values.get(f"capabilities.{name}", str(initial.get(f"capabilities.{name}", getattr(defaults, name))).lower())
        if value not in ("true", "false"):
            raise ValueError(f"capabilities.{name} must be true or false")
        capabilities[name] = value == "true"
    entry = dict(sdk=sdk, protocol=protocol, model=model, api_key_env=key_env,
                 context_window=context, max_output_tokens=output,
                 capabilities=capabilities, **setup_defaults(option_id, values))
    if url:
        entry["base_url"] = url
    ModelSpec.from_dict(profile, entry).require(tools=True, streaming=True)
    return profile, ordered_model_entry(entry)
