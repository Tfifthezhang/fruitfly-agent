"""Named text targets expose validation and host binding instructions."""
from dataclasses import dataclass
import hashlib
import re
from typing import Literal, Protocol, runtime_checkable
from fruitfly_agent.core.config import AgentLoopConfig

TEXT_TARGET_PREFIX = 'text-target:'


@dataclass(frozen=True)
class TargetBinding:
    kind: Literal['prompt', 'artifact']
    key: str = ''

    def __post_init__(self):
        if self.kind not in {'prompt', 'artifact'} or (self.kind == 'artifact' and not self.key):
            raise ValueError('invalid target binding')


@dataclass(frozen=True)
class TargetSnapshot:
    target_id: str
    text: str
    binding: TargetBinding
    schema: str = 'text-v1'

    def __post_init__(self):
        if not isinstance(self.target_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', self.target_id):
            raise ValueError('target identity must be a stable identifier')
        if not isinstance(self.text, str) or not isinstance(self.binding, TargetBinding):
            raise TypeError('target requires text and a typed binding')

    @property
    def content_hash(self):
        return 'sha256:' + hashlib.sha256(self.text.encode('utf-8')).hexdigest()


@runtime_checkable
class TextTarget(Protocol):
    def snapshot(self) -> TargetSnapshot: ...
    def validate(self, text: str) -> None: ...
    def prepare_trial(self, config: AgentLoopConfig, text: str) -> AgentLoopConfig: ...


def validate_text(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 30_000:
        raise ValueError('candidate text must contain 1–30,000 characters')
    if any(ord(char) < 32 and char not in '\n\t' for char in text):
        raise ValueError('candidate text contains control characters')
