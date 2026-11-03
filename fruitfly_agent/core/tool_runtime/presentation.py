"""Source-owned tool display facts, without terminal formatting or authority."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ToolPresentation:
    operation: str = 'generic'
    target: str = ''
    summary: str = ''
    items: int | None = None
    execution_state: str = ''

    def __post_init__(self):
        if self.operation not in {'generic', 'read', 'write', 'edit', 'execute', 'search', 'fetch'}:
            raise ValueError('invalid tool presentation operation')
        if any(not isinstance(value, str) or len(value) > 1000 for value in (self.target, self.summary)):
            raise ValueError('tool presentation text must be bounded')
        if self.items is not None and (type(self.items) is not int or self.items < 0):
            raise ValueError('tool item count must be nonnegative')
        if self.execution_state not in {'', 'running', 'succeeded', 'failed', 'cancelled', 'cleanup_unconfirmed'}:
            raise ValueError('invalid background execution state')

    def to_dict(self):
        return asdict(self)
