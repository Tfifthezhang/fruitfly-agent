"""Offline validation and form descriptions for the supported API protocols."""

import re
from urllib.parse import urlsplit

from .specs import ModelCapabilities, ModelSpec


CAPABILITY_OPTIONS = (
    ("tools", "Model tool calls; required by this harness", True),
    ("parallel_tool_calls", "Multiple tool calls in a single model response", False),
    ("vision", "Image input supported by the model and endpoint", False),
    ("reasoning", "Reasoning capability; does not enable reasoning parameters or lossless replay", False),
    ("streaming", "Streaming responses; required by this harness", True),
)


# Service labels are presentation defaults, never model capability presets.
SERVICES = (
    ("openai", "OpenAI official · Responses API", "openai", False),
    ("anthropic", "Anthropic official · Messages API", "anthropic", False),
    ("custom-responses", "Custom · Responses API", "openai", True),
    ("custom-messages", "Custom · Messages API", "anthropic", True),
)


def model_entry(option_id: str, values) -> tuple[str, dict]:
    service = next((item for item in SERVICES if item[0] == option_id), None)
    if service is None:
        raise ValueError("unsupported API service")
    profile = values.get("profile", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", profile):
        raise ValueError("models.<name> must use 1–80 letters, digits, dots, underscores, or hyphens")
    model = values.get("model", "").strip()
    if not model or any(ord(char) < 32 for char in model):
        raise ValueError("model must be non-empty text")
    url = values.get("base_url", "").strip()
    if service[3] and not url:
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
        value = values.get(f"capabilities.{name}", str(getattr(defaults, name)).lower())
        if value not in ("true", "false"):
            raise ValueError(f"capabilities.{name} must be true or false")
        capabilities[name] = value == "true"
    entry = dict(provider=service[2], model=model, api_key_env=key_env,
                 context_window=context, max_output_tokens=output,
                 capabilities=capabilities)
    if url:
        entry["base_url"] = url
    ModelSpec.from_dict(profile, entry).require(tools=True, streaming=True)
    return profile, entry
