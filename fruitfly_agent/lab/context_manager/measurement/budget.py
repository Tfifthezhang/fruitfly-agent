"""Bounded measurement with explicit quality, provider accounting and conservative calibration."""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, replace
import json
import math
import hashlib

from fruitfly_agent.core.context.budget import InputMeasurement, request_identity
from fruitfly_agent.core.data_model import ImageBlock
from fruitfly_agent.core.errors import FatalError
from fruitfly_agent.core.context.tasks import bounded_call
from .methods.heuristic.estimator import estimate_message_tokens, resolve_token_estimator


@dataclass(frozen=True)
class MeasurementConfig:
    token_estimator: str = 'heuristic_cjk'
    chars_per_token: float = 4.0
    margin_tokens: int = 128
    margin_ratio: float = .1
    provider_count: bool = False
    strict: bool = False
    count_timeout_seconds: float = 10.0
    calibration_samples: int = 32

    def __post_init__(self):
        resolve_token_estimator(self.token_estimator)
        for name in ('provider_count', 'strict'):
            if type(getattr(self, name)) is not bool:
                raise ValueError(name + ' must be boolean')
        for name, minimum, maximum in (('margin_tokens', 0, 100000), ('calibration_samples', 1, 256)):
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError('invalid measurement ' + name)
        for name, lower, upper in (('chars_per_token', 1, 8), ('margin_ratio', 0, 1), ('count_timeout_seconds', .01, 120)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper:
                raise ValueError('invalid measurement ' + name)
        if self.strict and not self.provider_count:
            raise ValueError('strict counting requires provider_count')


class MeasurementService:
    def __init__(self, config=None):
        self.config = config or MeasurementConfig()
        self.ratios: dict[tuple, deque] = {}
        self.raw: dict[str, tuple[tuple, int]] = {}
        self.counts: dict[tuple, int] = {}

    def validate_provider(self, provider):
        if self.config.strict and not getattr(provider, 'input_count_supported', False):
            raise ValueError('strict input counting is unsupported by this Provider')

    def text_tokens(self, text):
        base = resolve_token_estimator(self.config.token_estimator)(text)
        return math.ceil(base * 4 / self.config.chars_per_token)

    def estimate(self, view):
        tools = [t for t in view.tools if not t.hide_from_model]
        tokens = self.text_tokens(view.system_prompt) + 4
        tokens += sum(estimate_message_tokens(m, self.text_tokens) + 8 for m in view.messages)
        tokens += sum(self.text_tokens(json.dumps({'name': t.name, 'description': t.description,
            'parameters': t.parameters}, ensure_ascii=False)) + 12 for t in tools)
        return tokens

    async def measure(self, view, provider, *, signal=None):
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        identity = request_identity(view)
        output = view.max_tokens
        limit = getattr(provider, 'effective_output_limit', None)
        if callable(limit):
            output = limit(view)
        output = max(0, output)
        scope_fn = getattr(provider, 'input_measurement_scope', None)
        scope = scope_fn() if callable(scope_fn) else ''
        identity = 'sha256:' + hashlib.sha256(json.dumps((identity, scope, output), sort_keys=True).encode()).hexdigest()
        if self.config.provider_count and getattr(provider, 'input_count_supported', False):
            try:
                fingerprint = getattr(provider, 'input_count_identity', None)
                count_key = (id(provider), fingerprint(view)) if callable(fingerprint) else None
                value = self.counts.get(count_key) if count_key is not None else None
                if value is None:
                    value = await bounded_call(provider.count_input(view, signal=signal),
                        timeout=self.config.count_timeout_seconds, signal=signal)
                if type(value) is not int or value < 0:
                    raise ValueError('Provider input count must be a nonnegative integer')
                if count_key is not None:
                    self.counts[count_key] = value
                    while len(self.counts) > 64:
                        self.counts.pop(next(iter(self.counts)))
                return InputMeasurement(value, 'provider-count', 'exact', identity, output)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if isinstance(exc, FatalError) and isinstance(exc.details, dict) and exc.details.get('kind') == 'unconfirmed_cancellation':
                    raise
                if self.config.strict:
                    raise FatalError('strict input count unavailable', details={'kind': 'input_count_unavailable', 'error_type': type(exc).__name__}) from exc
        elif self.config.strict:
            raise FatalError('strict input counting is unsupported', details={'kind': 'input_count_unavailable'})
        estimation_view = view
        projection = getattr(provider, 'input_estimation_messages', None)
        if callable(projection):
            estimation_view = replace(view, messages=projection(view))
        raw = self.estimate(estimation_view)
        key = (id(provider), view.model, scope, tuple((t.name, t.description, json.dumps(t.parameters, sort_keys=True))
               for t in view.tools if not t.hide_from_model),
               any(getattr(m, 'provider_state', None) for m in view.messages))
        ratios = self.ratios.get(key, ())
        value = math.ceil(raw * max((1.0, *ratios)))
        self.raw[identity] = (key, raw)
        while len(self.raw) > 256: self.raw.pop(next(iter(self.raw)))
        uncertain = {'protocol-framing'}
        if any(isinstance(b, ImageBlock) for m in view.messages for b in getattr(m, 'content', ()) if not isinstance(getattr(m, 'content', None), str)):
            uncertain.add('image-estimate')
        if key[-1]: uncertain.add('opaque-continuation')
        margin = max(self.config.margin_tokens, math.ceil(value * self.config.margin_ratio))
        return InputMeasurement(value, self.config.token_estimator, 'heuristic', identity, output, margin, tuple(sorted(uncertain)))

    def observe(self, measurement, usage, provider):
        if usage is None or measurement.request_id not in self.raw:
            return
        normalize = getattr(provider, 'context_usage_tokens', None)
        if not callable(normalize):
            return
        actual = normalize(usage)
        if type(actual) is not int or actual <= 0:
            return
        key, raw = self.raw.pop(measurement.request_id)
        if raw:
            if len(self.ratios) >= 64 and key not in self.ratios:
                self.ratios.pop(next(iter(self.ratios)))
            self.ratios.setdefault(key, deque(maxlen=self.config.calibration_samples)).append(actual / raw)
