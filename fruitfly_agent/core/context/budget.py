"""Provider-neutral input measurements. Estimates never become exact by calibration."""
from __future__ import annotations

from dataclasses import dataclass
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
