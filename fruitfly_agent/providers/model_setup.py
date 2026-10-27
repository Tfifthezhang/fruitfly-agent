"""Offline validation and form descriptions for the supported API protocols."""

import re
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlsplit

from .specs import ModelCapabilities, ModelSpec
from .transport import TransportPolicy
from .services import service_definition


CAPABILITY_OPTIONS = (
    ("tools", "Model tool calls; required by this harness", True),
    ("parallel_tool_calls", "Multiple tool calls in a single model response", False),
    ("vision", "Image input supported by the model and endpoint", False),
    ("reasoning", "Reasoning capability; review the selected service's request defaults before saving", False),
    ("streaming", "Streaming responses; required by this harness", True),
)


@dataclass(frozen=True)
class SetupService:
    id: str
    label: str
    sdk: str
    protocol: str
    service: str
    description: str
    group: str
    custom: bool = False
    initial: dict = field(default_factory=dict)


# Explicit choices supply editable defaults; URLs and model names never select services.
SERVICES = (
    SetupService("openai", "OpenAI official · Responses API", "openai", "responses", "openai", "OpenAI account and API key. Uses the official address by default.", group="OpenAI"),
    SetupService("anthropic", "Anthropic official · Messages API", "anthropic", "messages", "anthropic", "Anthropic account and API key. Uses the official address by default.", group="Anthropic"),
    SetupService("deepseek", "DeepSeek · Responses API", "openai", "responses", "deepseek", "DeepSeek official API key. Flash defaults with high reasoning effort.", group="DeepSeek", initial={
        "profile": "DeepSeek-Flash", "model": "deepseek-flash", "base_url": "https://api.deepseek.com",
        "context_window": "1048576", "max_output_tokens": "32768", "api_key_env": "DEEPSEEK_API_KEY",
        "capabilities.parallel_tool_calls": True, "capabilities.vision": True, "capabilities.reasoning": True}),
    SetupService("qwen", "Qwen · Chat Completions API", "openai", "chat-completions", "qwen", "Qianwen AI Beijing endpoint. Qwen3.8-Flash defaults; confirm against your account and region.", group="Qwen", initial={
        "profile": "Qwen3.8-Flash", "model": "qwen3.8-flash",
        "base_url": "https://cn-beijing.maas.qianwenaiapi.com/compatible-mode/v1",
        "context_window": "1000000", "max_output_tokens": "32768", "api_key_env": "DASHSCOPE_API_KEY",
        "capabilities.parallel_tool_calls": True, "capabilities.vision": True, "capabilities.reasoning": True}),
    SetupService("bigmodel", "Zhipu BigModel · Chat Completions API", "openai", "chat-completions", "bigmodel", "BigModel China API key. GLM-4.5-Air text-only defaults; confirm against your selected model.", group="Zhipu BigModel", initial={
        "profile": "GLM-4.5-Air", "model": "glm-4.5-air",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "context_window": "131072", "max_output_tokens": "32768", "api_key_env": "ZAI_API_KEY",
        "capabilities.reasoning": True}),
    SetupService("custom-responses", "Responses API", "openai", "responses", "generic", "Gateway or self-hosted Responses API. Requires its API address and key.", group="Custom service…", custom=True),
    SetupService("custom-messages", "Messages API", "anthropic", "messages", "generic", "Gateway or self-hosted Messages API. Requires its API address and key.", group="Custom service…", custom=True),
    SetupService("custom-chat", "Chat Completions API", "openai", "chat-completions", "generic", "Gateway or self-hosted Chat Completions. Requires its API address and key.", group="Custom service…", custom=True),
)


def setup_selection(option_id: str, field: str, values, pairs: tuple[tuple[str, str], ...]) -> tuple[str, tuple[str, ...]]:
    selected = next((item for item in SERVICES if item.id == option_id), None)
    if selected is None or field not in {'sdk', 'protocol'}:
        raise ValueError('unsupported model setup selection')
    definition = service_definition(selected.service, selected.protocol)
    pairs = tuple((sdk, protocol) for sdk, protocol in pairs
                  if (selected.service == 'generic' or protocol in definition.protocols)
                  and (selected.custom or protocol == selected.protocol))
    sdks = tuple(dict.fromkeys(sdk for sdk, protocol in pairs))
    sdk = values.get('sdk', selected.sdk)
    if field == 'sdk':
        return sdk if sdk in sdks else next(iter(sdks), ''), sdks
    choices = tuple(protocol for client, protocol in pairs if client == sdk)
    value = values.get('protocol', selected.protocol)
    return value if value in choices else next(iter(choices), ''), choices


def setup_defaults(option_id: str, values) -> dict:
    selected = next((item for item in SERVICES if item.id == option_id), None)
    if selected is None:
        raise ValueError("unsupported API service")
    reasoning = values.get("capabilities.reasoning", str(selected.initial.get("capabilities.reasoning", False)).lower()) == "true"
    parameters: dict[str, Any] = {}
    protocol = values.get('protocol', selected.protocol)
    if selected.service == "deepseek":
        if protocol == 'responses':
            parameters = {"reasoning": {"effort": "high" if reasoning else "none"}}
        elif protocol == 'messages':
            parameters = {'thinking': {'type': 'enabled' if reasoning else 'disabled'}}
            if reasoning:
                parameters['output_config'] = {'effort': 'high'}
        elif protocol == 'chat-completions':
            parameters = {'extra_body': {'thinking': {'type': 'enabled' if reasoning else 'disabled'}}}
            if reasoning:
                parameters['reasoning_effort'] = 'high'
    elif selected.service == "qwen":
        extra: dict[str, Any] = {"enable_thinking": reasoning, "preserve_thinking": reasoning}
        if reasoning:
            extra["reasoning_effort"] = "medium"
        parameters = {"extra_body": extra}
    elif selected.service == "bigmodel":
        parameters = {"extra_body": {"thinking": {"type": "enabled" if reasoning else "disabled"}}}
    return {"service": selected.service, "parameters": parameters,
            "transport": {**asdict(TransportPolicy()), "retry_max": 3, "retry_base_delay": 1.0}}


def model_entry(option_id: str, values) -> tuple[str, dict]:
    service = next((item for item in SERVICES if item.id == option_id), None)
    if service is None:
        raise ValueError("unsupported API service")
    profile = values.get("profile", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", profile):
        raise ValueError("models.<name> must use 1–80 letters, digits, dots, underscores, or hyphens")
    model = values.get("model", "").strip()
    if not model or any(ord(char) < 32 for char in model):
        raise ValueError("model must be non-empty text")
    url = values.get("base_url", "").strip()
    url = url or str(service.initial.get("base_url", ""))
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
        value = values.get(f"capabilities.{name}", str(service.initial.get(f"capabilities.{name}", getattr(defaults, name))).lower())
        if value not in ("true", "false"):
            raise ValueError(f"capabilities.{name} must be true or false")
        capabilities[name] = value == "true"
    entry = dict(sdk=values.get('sdk', service.sdk), protocol=values.get('protocol', service.protocol), model=model, api_key_env=key_env,
                 context_window=context, max_output_tokens=output,
                 capabilities=capabilities, **setup_defaults(option_id, values))
    if url:
        entry["base_url"] = url
    ModelSpec.from_dict(profile, entry).require(tools=True, streaming=True)
    return profile, entry
