"""Idempotent model-projection adapter for a runtime's scanned Skill catalog."""

from __future__ import annotations

from dataclasses import dataclass, replace

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
    max_chars: int = 16_000

    def __post_init__(self) -> None:
        if isinstance(self.max_chars, bool) or not isinstance(self.max_chars, int) or self.max_chars < 128:
            raise ValueError("max_chars must be an integer >= 128")

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
                block = f"{_START}\nSkill catalog omitted: max_chars exceeded.\n{_END}"
            prompt = f"{prompt}\n\n{block}" if prompt else block
        if prompt == frame.system_prompt:
            return None
        return ContextTransform(
            replace(frame, system_prompt=prompt), metadata={"catalog_omitted": omitted},
        )


__all__ = ["SkillCatalogTransformer"]
