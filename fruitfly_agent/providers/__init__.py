"""Model-provider adapters and reproducible model specifications.

Providers depend on the frozen core protocol; core never imports a vendor.
"""

from .anthropic import AnthropicProvider
from .config import load_env
from .openai import OpenAIProvider
from .chat_completions import ChatCompletionsProvider
from .registry import ProviderRegistry, default_registry
from .specs import ModelCapabilities, ModelSpec, ProviderSpec

__all__ = [
    "AnthropicProvider",
    "load_env",
    "OpenAIProvider",
    "ChatCompletionsProvider",
    "ProviderRegistry",
    "default_registry",
    "ModelCapabilities",
    "ModelSpec",
    "ProviderSpec",
]
