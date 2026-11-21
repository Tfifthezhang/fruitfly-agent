"""OpenCode Go subscription connection."""
from ...contracts import ConnectionDefinition
from ....auth.contracts import AuthMethod
from ....services import service_definition
from .catalog import parse_models
from .requests import GoRequests

def definition() -> ConnectionDefinition:
    return ConnectionDefinition('opencode-go', 'OpenCode Go', 'opencode-go', 'chat-completions', 'openai',
        service_definition('opencode-go', 'chat-completions').base_url or '',
        AuthMethod('key', 'Subscription key', 'key', 'https://opencode.ai/console'), parse_models,
        request_policy=GoRequests())
