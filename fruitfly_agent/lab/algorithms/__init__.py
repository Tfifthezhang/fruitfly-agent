"""Algorithm identity independent of execution and host lifecycle."""
from dataclasses import dataclass
import re
from typing import Literal


@dataclass(frozen=True)
class AlgorithmSpec:
    algorithm_id: str
    implementation_id: str
    state_scope: Literal['request', 'run', 'session', 'workspace'] = 'request'

    def __post_init__(self):
        if any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value) for value in (self.algorithm_id, self.implementation_id)):
            raise ValueError('algorithm and implementation identities must not be empty')
        if self.state_scope not in {'request', 'run', 'session', 'workspace'}:
            raise ValueError('invalid algorithm state scope')


class Algorithm:
    """Identity only; execution remains governed by the relevant Core/Lab protocol."""
    spec: AlgorithmSpec
