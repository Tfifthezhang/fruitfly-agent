"""Shared bounded auxiliary requests; methods own their prompts and coverage policy."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from fruitfly_agent.core.context.tasks import bounded_call
from fruitfly_agent.core.data_model import ProviderView, UserMessage
from fruitfly_agent.core.errors import FatalError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuxiliaryResult:
    text: str = ''
    outcome: str = 'failed'
    reason: str = ''
    elapsed_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


class AuxiliaryText:
    def __init__(self, provider, *, model=None, context_window=None, output_limit=None, meter=None):
        self.provider, self.model = provider, model
        self.context_window, self.output_limit = context_window, output_limit
        self.meter = meter

    async def request_once(self, snapshot, *, system, prompt, max_tokens, timeout,
                           input_limit, estimate):
        """One operation deadline includes input measurement, streaming and cleanup."""
        started = time.monotonic()
        async def consume():
            output = min(max_tokens, self.output_limit or max_tokens)
            view = ProviderView(system, [UserMessage(prompt)], [], self.model or snapshot.model, output)
            tokens = estimate(system + prompt) + 32
            if self.meter is not None:
                measured = await self.meter.measure(view, self.provider, signal=snapshot.signal)
                tokens = measured.input_tokens
                if self.context_window is not None and not measured.fits(self.context_window):
                    return AuxiliaryResult(reason='input_capacity')
            if tokens is None or tokens > input_limit or self.context_window is not None and tokens + output > self.context_window:
                return AuxiliaryResult(reason='input_capacity')
            stream = self.provider(view, signal=snapshot.signal)
            try:
                async for _ in stream:
                    pass
                final = await stream.result()
                usage = final.usage
                reason = ('truncated' if final.stop_reason == 'length' else
                    'invalid_output' if final.stop_reason != 'stop' or final.tool_calls or final.continue_turn else
                    'empty' if not final.text.strip() else '')
                return AuxiliaryResult(final.text.strip() if not reason else '',
                    'failed' if reason else 'succeeded', reason,
                    input_tokens=usage.input_tokens if usage else 0,
                    output_tokens=usage.output_tokens if usage else 0)
            finally:
                await stream.aclose()
        try:
            result = await bounded_call(consume(), timeout=timeout, signal=snapshot.signal)
        except asyncio.CancelledError:
            raise
        except FatalError as exc:
            if isinstance(exc.details, dict) and exc.details.get('kind') in {
                    'model_budget_exhausted', 'unconfirmed_cancellation'}:
                raise
            result = AuxiliaryResult(reason='provider_error')
        except TimeoutError:
            result = AuxiliaryResult(reason='timeout')
        except Exception:
            result = AuxiliaryResult(reason='provider_error')
        from dataclasses import replace
        return replace(result, elapsed_seconds=time.monotonic() - started)

    async def request_bounded(self, snapshot, *, deadline, timeout, attempts, **request):
        started = time.monotonic()
        result = AuxiliaryResult(reason='maintenance_deadline')
        for _ in range(attempts):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            result = await self.request_once(snapshot, timeout=min(timeout, remaining), **request)
            if result.outcome == 'succeeded' or result.reason not in {'provider_error', 'timeout'}:
                break
        from dataclasses import replace
        return replace(result, elapsed_seconds=time.monotonic() - started)

    async def request(self, snapshot, *, system, prompt, max_tokens, timeout, attempts, estimate):
        result = await self.request_bounded(snapshot, deadline=time.monotonic() + timeout,
            timeout=timeout, attempts=attempts, system=system, prompt=prompt,
            max_tokens=max_tokens, estimate=estimate, input_limit=2**63-1)
        return result.text if result.outcome == 'succeeded' else None

    def page_size(self, text, *, system, build_prompt, max_chars, max_tokens, estimate):
        """Largest complete character prefix that fits; never omit a middle range."""
        high = min(len(text), max_chars)
        if self.context_window is None:
            return high
        output = min(max_tokens, self.output_limit or max_tokens)
        low = 0
        while low < high:
            middle = (low + high + 1) // 2
            if estimate(system + build_prompt(text[:middle])) + output + 32 <= self.context_window:
                low = middle
            else:
                high = middle - 1
        return low
