"""Explicit checkpoint/version lineage; no implied backend snapshot support."""
from dataclasses import dataclass
from ..contracts.validation import identifier
from ..contracts.versions import require_hash


@dataclass(frozen=True)
class ExecutionSegment:
    segment_id: str
    version_id: str
    initial_state_id: str
    parent_segment_id: str = ''
    checkpoint_id: str = ''
    transfer_id: str = ''

    def __post_init__(self):
        identifier(self.segment_id)
        require_hash(self.version_id)
        require_hash(self.initial_state_id)
        if self.parent_segment_id:
            identifier(self.parent_segment_id)
            require_hash(self.checkpoint_id)
            require_hash(self.transfer_id)
            if self.segment_id == self.parent_segment_id:
                raise ValueError('segment cannot parent itself')
        elif self.checkpoint_id or self.transfer_id:
            raise ValueError('continuation evidence requires a parent segment')
