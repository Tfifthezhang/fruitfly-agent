"""Offline SDK streams and construction helpers shared by Provider tests."""
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch
from fruitfly_agent.core.data_model import ProviderView, UserMessage
from fruitfly_agent.providers.openai import OpenAIProvider
from fruitfly_agent.providers.anthropic import AnthropicProvider

class SDKStream:
    def __init__(self, events=(), final=None):
        self.events = iter(events)
        self.final = final
        self.exited = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            event = next(self.events)
        except StopIteration:
            raise StopAsyncIteration
        if isinstance(event, BaseException):
            raise event
        return event

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.exited = True

    async def get_final_message(self):
        return self.final

    async def close(self):
        self.exited = True


def view(tools=()):
    return ProviderView('instructions', [UserMessage(content='hello')], list(tools), 'chosen-model', 32)


def adapter(kind, streams, **options):
    if kind == 'openai':
        client = NS(responses=NS(create=AsyncMock(side_effect=streams)))
        with patch('openai.AsyncOpenAI', return_value=client):
            provider = OpenAIProvider(api_key='offline-placeholder', model='fallback', retry_base_delay=0, **options)
        request = client.responses.create
    else:
        client = NS(messages=NS(stream=Mock(side_effect=streams)))
        with patch('anthropic.AsyncAnthropic', return_value=client):
            provider = AnthropicProvider(api_key='offline-placeholder', model='fallback', retry_base_delay=0, **options)
        request = client.messages.stream
    return provider, request


