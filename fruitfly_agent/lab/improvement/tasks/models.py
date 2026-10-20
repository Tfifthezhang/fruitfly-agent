"""Private verification cases, kept separate from editor task materials."""
from dataclasses import dataclass
from ..contracts.versions import content_hash

@dataclass(frozen=True)
class TaskCase:
    input: str
    expected: str
    verification: str = ""

    def __post_init__(self):
        if not isinstance(self.input, str) or not isinstance(self.expected, str):
            raise ValueError("case fields must be strings")
        if not self.input.strip() or not self.expected.strip():
            raise ValueError("case input and expected must not be empty")
        if not isinstance(self.verification, str) or len(self.verification) > 16000:
            raise ValueError("verification must be bounded immutable text")
        if len(self.input) > 4000 or len(self.expected) > 1000:
            raise ValueError("case exceeds the text size limit")

    @property
    def case_id(self):
        return content_hash(self.input + "\0" + self.expected + ("\0" + self.verification if self.verification else ""))

