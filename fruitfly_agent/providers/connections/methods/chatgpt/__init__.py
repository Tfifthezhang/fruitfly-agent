"""ChatGPT plan access using the public Responses endpoint."""
from ...contracts import ConnectionDefinition
from ....auth.contracts import AuthMethod
from ....services import service_definition
from .catalog import parse_models
from .requests import ChatGPTRequests
from .auth import refresh, authorization_url, complete, revoke, begin_login

def definition() -> ConnectionDefinition:
    return ConnectionDefinition('chatgpt', 'ChatGPT', 'chatgpt', 'responses', 'openai',
        service_definition('chatgpt', 'responses').base_url or '',
        AuthMethod('oauth', 'Continue with ChatGPT', 'oauth'), parse_models,
        refresh=refresh, request_policy=ChatGPTRequests(), output_enforced=False,
        begin_login=begin_login, authorization_url=authorization_url, complete_login=complete, revoke=revoke)
