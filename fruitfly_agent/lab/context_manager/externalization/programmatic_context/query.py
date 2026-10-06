"""Bounded auxiliary-model calls exposed to the IPython host bridge."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
import uuid
from typing import Any

from fruitfly_agent.core.data_model.messages import UserMessage
from fruitfly_agent.core.data_model.runtime import ProviderView
from fruitfly_agent.core.extensions.protocols import Provider

from .artifacts import SessionArtifactStore


@dataclass(frozen=True)
class ModelQueryConfig:
    max_calls: int = 16
    max_concurrent: int = 4
    max_input_chars: int = 200_000
    max_output_tokens: int = 4_096
    max_total_tokens: int = 100_000
    max_inline_result_chars: int = 100_000
    timeout_seconds: int = 180


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

        estimated = max(1, input_chars // 4) + max_tokens
        async with self._lock:
            if self._calls >= self.config.max_calls:
                raise RuntimeError(
                    f"model.query call budget exhausted ({self.config.max_calls})"
                )
            if self._tokens + estimated > self.config.max_total_tokens:
                raise RuntimeError(
                    "model.query token budget exhausted "
                    f"({self.config.max_total_tokens})"
                )
            self._calls += 1
            self._tokens += estimated

        call_id = uuid.uuid4().hex
        started = time.monotonic()
        async with self._semaphore:
            view = ProviderView(
                system_prompt=system_prompt or (
                    "Answer the supplied subproblem directly. Return text only; "
                    "do not call tools or assume access to the parent conversation."
                ),
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
                self._tokens += actual - estimated
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
            "estimated_or_actual_tokens": self._tokens,
            "max_calls": self.config.max_calls,
            "max_total_tokens": self.config.max_total_tokens,
        }


__all__ = ["ModelQueryBroker", "ModelQueryConfig"]
