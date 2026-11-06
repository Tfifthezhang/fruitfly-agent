"""Idempotent model-projection adapter for a runtime's scanned Skill catalog."""

from __future__ import annotations

from dataclasses import dataclass, replace, field
from fruitfly_agent.runtime_spec.documents import parameter_default

from fruitfly_agent.core.context import ContextFrame, ContextTransform

_START = "<!-- fruitfly:skill-catalog:start -->"
_END = "<!-- fruitfly:skill-catalog:end -->"


@dataclass(frozen=True)
class SkillCatalogTransformer:
    """Replace the catalog block without scanning files or changing messages.

    ``guidance`` is the catalog rendering injected at assembly time.
    An empty rendering removes a previously projected complete block.
    """

    guidance: str
    max_chars: int = field(default_factory=lambda: parameter_default(__package__, 'defaults.yaml', 'settings.max_chars'))
    directory: str = ''

    def __post_init__(self) -> None:
        if isinstance(self.max_chars, bool) or not isinstance(self.max_chars, int) or self.max_chars < 128:
            raise ValueError("max_chars must be an integer >= 128")
        if self.directory and len(f'{_START}\nRead Skills: {self.directory}\n{_END}') > self.max_chars:
            raise ValueError('max_chars cannot hold the complete Skill directory reference')

    def transform(self, frame: ContextFrame) -> ContextTransform | None:
        prompt = frame.system_prompt
        removed = False
        while True:
            start = prompt.find(_START)
            end = prompt.find(_END, start + len(_START)) if start >= 0 else -1
            if end < 0:
                break
            prompt = prompt[:start] + prompt[end + len(_END):]
            removed = True
        if not removed and not self.guidance:
            return None
        prompt = prompt.rstrip()
        omitted = False
        if self.guidance:
            block = f"{_START}\n{self.guidance}\n{_END}"
            if len(block) > self.max_chars:
                omitted = True
                fallback = ('Read Skills: ' + self.directory if self.directory else
                            'Skill catalog omitted: max_chars exceeded.')
                block = f"{_START}\n{fallback}\n{_END}"
            prompt = f"{prompt}\n\n{block}" if prompt else block
        if prompt == frame.system_prompt:
            return None
        return ContextTransform(
            replace(frame, system_prompt=prompt), metadata={"catalog_omitted": omitted},
        )


__all__ = ["SkillCatalogTransformer"]
