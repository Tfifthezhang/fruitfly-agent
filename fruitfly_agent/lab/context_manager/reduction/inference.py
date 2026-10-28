"""Shared bounded auxiliary requests; methods own their prompts and coverage policy."""
from __future__ import annotations

import asyncio
import logging
from fruitfly_agent.core.context.tasks import bounded_call
from fruitfly_agent.core.data_model import ProviderView, UserMessage
from fruitfly_agent.core.errors import FatalError

logger = logging.getLogger(__name__)


class AuxiliaryText:
    def __init__(self, provider, *, model=None, context_window=None, output_limit=None, meter=None):
        self.provider, self.model = provider, model
        self.context_window, self.output_limit = context_window, output_limit
        self.meter = meter

    async def request(self, snapshot, *, system, prompt, max_tokens, timeout, attempts, estimate):
        output = min(max_tokens, self.output_limit or max_tokens)
        if self.context_window is not None and estimate(system + prompt) + output + 32 > self.context_window:
            return None
        view = ProviderView(system, [UserMessage(prompt)], [], self.model or snapshot.model, output)
        measurement = None
        if self.meter is not None:
            measurement = await self.meter.measure(view, self.provider, signal=snapshot.signal)
            if self.context_window is not None and not measurement.fits(self.context_window):
                return None
        async def consume():
            stream = self.provider(view, signal=snapshot.signal)
            try:
                async for _ in stream:
                    pass
                final = await stream.result()
                observe = getattr(self.meter, 'observe', None)
                if callable(observe) and measurement is not None:
                    try:
                        observe(measurement, final.usage, self.provider)
                    except Exception:
                        logger.warning('auxiliary usage calibration failed', exc_info=True)
                if final.stop_reason != 'stop' or final.tool_calls or final.continue_turn:
                    return None
                return final.text.strip() or None
            finally:
                await stream.aclose()
        for _ in range(attempts):
            try:
                return await bounded_call(consume(), timeout=timeout, signal=snapshot.signal)
            except asyncio.CancelledError:
                raise
            except FatalError:
                # Outer model allowance and unconfirmed effects cannot be retried here.
                raise
            except Exception as exc:
                logger.warning('auxiliary context request failed: %s', type(exc).__name__)
        return None

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
