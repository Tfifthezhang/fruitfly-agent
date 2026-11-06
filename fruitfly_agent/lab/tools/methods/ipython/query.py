"""Bounded auxiliary-model calls exposed to the IPython host bridge."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from fruitfly_agent.runtime_spec.documents import parameter_default
import time
import uuid
from typing import Any

from fruitfly_agent.core.data_model.messages import UserMessage
from fruitfly_agent.core.data_model.runtime import ProviderView
from fruitfly_agent.core.extensions.protocols import Provider

from fruitfly_agent.lab.tools.methods.ipython.artifacts import SessionArtifactStore


@dataclass(frozen=True)
class ModelQueryConfig:
    max_concurrent: int = field(default_factory=lambda: parameter_default('fruitfly_agent.lab.tools.methods.ipython', 'defaults.yaml', 'settings.max_query_concurrent'))
    max_input_chars: int = field(default_factory=lambda: parameter_default('fruitfly_agent.lab.tools.methods.ipython', 'defaults.yaml', 'settings.max_query_input_chars'))
    max_output_tokens: int = field(default_factory=lambda: parameter_default('fruitfly_agent.lab.tools.methods.ipython', 'defaults.yaml', 'settings.max_query_output_tokens'))
    max_inline_result_chars: int = field(default_factory=lambda: parameter_default('fruitfly_agent.lab.tools.methods.ipython', 'defaults.yaml', 'settings.max_query_inline_result_chars'))
    timeout_seconds: int = field(default_factory=lambda: parameter_default('fruitfly_agent.lab.tools.methods.ipython', 'defaults.yaml', 'settings.query_timeout_seconds'))
    instructions: str = field(default_factory=lambda: parameter_default(
        'fruitfly_agent.lab.tools.methods.ipython', 'defaults.yaml', 'instructions.query'))


class ModelQueryBroker:
    """Host-authoritative, depth-one text model query broker."""

    def __init__(
        self,
        provider: Provider,
        *,
        model: str,
        profile: str,
        store: SessionArtifactStore,
        config: ModelQueryConfig,
    ) -> None:
        self.provider = provider
        self.model = model
        self.profile = profile
        self.store = store
        self.config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrent)
        self._lock = asyncio.Lock()
        self._calls = 0
        self._tokens = 0

    async def handle(
        self,
        request_type: str,
        payload: dict[str, Any],
        *,
        signal: asyncio.Event | None = None,
    ) -> dict[str, Any]:
        if request_type != "model.query":
            raise ValueError(f"unsupported RLM host request: {request_type!r}")
        prompt = payload.get("prompt")
        system_prompt = payload.get("system_prompt", "")
        requested_tokens = payload.get("max_output_tokens")
        if not isinstance(prompt, str) or not prompt:
            raise ValueError("model.query prompt must be a non-empty string")
        if len(prompt) > self.config.max_input_chars:
            raise ValueError(
                f"model.query prompt has {len(prompt)} characters; "
                f"limit is {self.config.max_input_chars}"
            )
        if not isinstance(system_prompt, str):
            raise ValueError("model.query system_prompt must be a string")
        system_prompt = system_prompt or self.config.instructions
        input_chars = len(prompt) + len(system_prompt)
        if input_chars > self.config.max_input_chars:
            raise ValueError(
                f"model.query input has {input_chars} characters; "
                f"limit is {self.config.max_input_chars}"
            )
        if requested_tokens is None:
            max_tokens = self.config.max_output_tokens
        elif (
            isinstance(requested_tokens, bool)
            or not isinstance(requested_tokens, int)
            or requested_tokens < 1
        ):
            raise ValueError("model.query max_output_tokens must be positive")
        else:
            max_tokens = min(requested_tokens, self.config.max_output_tokens)

        async with self._lock:
            self._calls += 1

        call_id = uuid.uuid4().hex
        started = time.monotonic()
        async with self._semaphore:
            view = ProviderView(
                system_prompt=system_prompt,
                messages=[UserMessage(content=prompt)],
                tools=[],
                model=self.model,
                max_tokens=max_tokens,
            )
            async with asyncio.timeout(self.config.timeout_seconds):
                assistant = await self.provider(view, signal=signal).result()
        usage = assistant.usage
        if usage is not None:
            actual = usage.total_tokens
            async with self._lock:
                self._tokens += actual
        if assistant.continue_turn:
            raise RuntimeError('model.query requires a final single-response result; the model returned an intermediate response')
        text = assistant.text
        result: dict[str, Any] = {
            "call_id": call_id,
            "model_profile": self.profile,
            "model": self.model,
            "stop_reason": assistant.stop_reason,
            "usage": usage.to_dict() if usage is not None else None,
            "latency_ms": round((time.monotonic() - started) * 1000),
            "text": text,
            "reference": None,
        }
        if len(text) > self.config.max_inline_result_chars:
            artifact = self.store.put_text(
                text,
                kind="model-query-result",
                origin=f"model-query:{call_id}",
            )
            result["text"] = text[:2_000]
            result["reference"] = artifact.reference
        return result

    async def health(self) -> dict[str, Any]:
        return {
            "status": "ready",
            "calls": self._calls,
            "reported_tokens": self._tokens,
        }


__all__ = ["ModelQueryBroker", "ModelQueryConfig"]
