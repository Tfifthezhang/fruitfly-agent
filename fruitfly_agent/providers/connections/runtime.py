"""Attach renewable account auth to a protocol adapter without replacing its loop."""
from __future__ import annotations
import asyncio
from typing import Any, AsyncIterator, Mapping
from uuid import uuid4
from fruitfly_agent.core.context.budget import forward_context_capabilities
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamEvent, StreamDone
from fruitfly_agent.core.data_model import ProviderView
from ..auth.contracts import ModelAuthorization, CredentialStore
from ..specs import ModelSpec
from pathlib import Path


def model_authorization(spec: ModelSpec, environment: Mapping[str, str], *,
                        credential_store: CredentialStore | None = None,
                        binding_directory: Path | None = None) -> ModelAuthorization:
    """Resolve host authorization without constructing a model client."""
    from .contracts import ConnectionProfile
    from .registry import builtin_connections
    from ..auth.environment import EnvironmentAuthorization
    from ..auth.session import AuthSession
    from ..auth.stores import configured_store
    if spec.access is None:
        raise ValueError('Model authorization requires a connection')
    connection = ConnectionProfile.from_dict(spec.access)
    definition = builtin_connections().get(connection.integration)
    if connection.credential_env:
        return EnvironmentAuthorization(connection.integration, connection.credential_env,
            environment, binding_directory=binding_directory)
    return AuthSession(credential_store or configured_store(), connection.account,
        definition.id, definition.refresh)

class ConnectedProvider:
    def __init__(self, provider: Any, auth: ModelAuthorization, *, output_enforced: bool, output_reserve: int):
        self.provider, self.auth = provider, auth
        self.output_enforced, self.output_reserve = output_enforced, output_reserve
        self.transport_parameters = provider.transport_parameters
        self.connection_identity = {'integration': auth.integration, 'account_binding': auth.identity,
                                    'output_enforced': output_enforced, 'output_reserve': output_reserve}
        self.service_usage = provider.service_usage
        self.connection_status = {'integration': auth.integration, 'account': auth.account, 'account_label': auth.label, 'output_enforced': output_enforced, 'output_reserve': output_reserve}
        self.session_id = uuid4().hex
        forward_context_capabilities(self, provider)
        self.input_count_supported = False
        if not output_enforced:
            self.effective_output_limit = lambda view: output_reserve

    def bind_session(self, session_id: str) -> None:
        self.provider.bind_session(session_id)

    def __call__(self, view: ProviderView, *, signal: asyncio.Event | None = None) -> AssistantMessageEventStream:
        async def events() -> AsyncIterator[StreamEvent]:
            self.service_usage.clear()
            token = await self.auth.token(signal)
            self.provider.set_access_token(token)
            inner = self.provider(view, signal=signal)
            try:
                async for event in inner:
                    yield event
                yield StreamDone(await inner.result())
            finally:
                await inner.aclose()
        return AssistantMessageEventStream(events())

    async def close(self) -> None:
        await self.provider.close()
