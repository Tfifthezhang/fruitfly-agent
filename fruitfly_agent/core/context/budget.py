"""Provider-neutral input measurements. Estimates never become exact by calibration."""
from __future__ import annotations

from dataclasses import dataclass, field
from ..configuration_resources import package_parameter
import hashlib
import json
from typing import Any, Protocol


@dataclass(frozen=True)
class InputMeasurement:
    input_tokens: int | None
    source: str
    quality: str
    request_id: str
    output_reserve: int
    margin: int = 0
    uncertain: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.input_tokens is not None and (type(self.input_tokens) is not int or self.input_tokens < 0):
            raise ValueError('input tokens must be nonnegative or unknown')
        if self.quality not in {'exact', 'tokenizer', 'heuristic', 'unknown'}:
            raise ValueError('unknown input measurement quality')
        if self.quality == 'exact' and (self.input_tokens is None or self.uncertain):
            raise ValueError('an exact measurement cannot contain uncounted inputs')
        if any(type(v) is not int or v < 0 for v in (self.output_reserve, self.margin)):
            raise ValueError('output reserve and uncertainty margin must be nonnegative')

    def fits(self, window: int) -> bool:
        return self.input_tokens is not None and self.input_tokens + self.output_reserve + self.margin <= window


class ContextMeter(Protocol):
    async def measure(self, view: Any, provider: Any, *, signal: Any = None) -> InputMeasurement: ...


@dataclass(frozen=True)
class ContextBudget:
    """Shared input capacity, including uncertainty but excluding output reserve."""

    max_input_tokens: int = field(default_factory=lambda: package_parameter(__package__, 'defaults.yaml', 'settings.max_input_tokens'), metadata={'description': 'Protected working input ceiling including uncertainty; independent of model capacity.', 'minimum': 1024, 'maximum': 1048576})
    trigger_ratio: float = field(default_factory=lambda: package_parameter(__package__, 'defaults.yaml', 'settings.trigger_ratio'), metadata={'description': 'Working-capacity fraction that requests reduction.', 'minimum': .1, 'maximum': .95})
    target_ratio: float = field(default_factory=lambda: package_parameter(__package__, 'defaults.yaml', 'settings.target_ratio'), metadata={'description': 'Desired working-capacity fraction after reduction.', 'minimum': .05, 'maximum': .9})

    def __post_init__(self) -> None:
        import math
        if type(self.max_input_tokens) is not int or not 1024 <= self.max_input_tokens <= 1048576:
            raise ValueError('max_input_tokens must be an integer within [1024, 1048576]')
        for value in (self.trigger_ratio, self.target_ratio):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('context budget ratios must be finite numbers')
        if not (.05 <= self.target_ratio <= .9 and .1 <= self.trigger_ratio <= .95
                and self.target_ratio < self.trigger_ratio):
            raise ValueError('context budget requires 0 < target_ratio < trigger_ratio < 1')

    def input_allowance(self, window: int, measurement: InputMeasurement | None, max_tokens: int) -> int:
        reserve = measurement.output_reserve if measurement is not None else max_tokens
        margin = measurement.margin if measurement is not None else 0
        return max(0, min(self.max_input_tokens, window - reserve) - margin)

    def capacity(self, window: int, measurement: InputMeasurement) -> int:
        return max(0, min(self.max_input_tokens, window - measurement.output_reserve))

    def fits(self, window: int, measurement: InputMeasurement) -> bool:
        return (measurement.fits(window) and measurement.input_tokens is not None
                and measurement.input_tokens + measurement.margin <= self.capacity(window, measurement))


def request_identity(view: Any) -> str:
    """Hash effective public request inputs, including opaque replay and hidden-tool status."""
    data = {'model': view.model, 'system': view.system_prompt, 'output': view.max_tokens,
        'messages': [m.to_dict() for m in view.messages],
        'tools': [{'name': t.name, 'description': t.description, 'parameters': t.parameters}
                  for t in view.tools if not t.hide_from_model]}
    encoded = json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return 'sha256:' + hashlib.sha256(encoded.encode()).hexdigest()


def forward_context_capabilities(target: Any, source: Any) -> None:
    """A transparent Provider wrapper must preserve counting and replay capabilities."""
    for name in ('count_input', 'input_count_supported', 'can_rebase_context', 'context_usage_tokens',
                 'effective_output_limit', 'input_count_identity', 'input_measurement_scope',
                 'input_estimation_messages', 'validate_input', 'vision'):
        if hasattr(source, name):
            setattr(target, name, getattr(source, name))
