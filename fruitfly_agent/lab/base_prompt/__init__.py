"""Immutable base prompts; Run resolves selection and owns artifact storage."""

from __future__ import annotations
from fruitfly_agent.runtime_spec.documents import parameter_default

from dataclasses import dataclass
import hashlib


DEFAULT_PROMPT_ID = "assistant-default"


@dataclass(frozen=True)
class BasePrompt:
    prompt_id: str
    label: str
    text: str

    @property
    def content_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def _default_prompt():
    return BasePrompt(DEFAULT_PROMPT_ID, 'Assistant default',
        parameter_default(__package__, 'defaults.yaml', 'instructions.system'))


DEFAULT_PROMPT = _default_prompt()


def builtins() -> tuple[BasePrompt, ...]:
    """Return the project's own default from its registered parameter document."""
    return (_default_prompt(),)


def get_builtin(prompt_id: str) -> BasePrompt:
    for prompt in builtins():
        if prompt.prompt_id == prompt_id:
            return prompt
    raise ValueError(f"unknown built-in base prompt: {prompt_id!r}")


__all__ = ["BasePrompt", "DEFAULT_PROMPT_ID", "DEFAULT_PROMPT", "builtins", "get_builtin"]
