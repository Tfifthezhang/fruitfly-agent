"""Attributable stage failures; cancellation and integrity errors are not retries."""
from dataclasses import dataclass
from .validation import identifier


class IntegrityError(ValueError):
    """A receipt, source or immutable identity differs from the granted conditions."""


class PersistenceError(IntegrityError):
    """The host could not durably record a workflow fact; work must stop."""


class CleanupError(IntegrityError):
    """Retirement of owned work was not confirmed; do not schedule more work."""


@dataclass(frozen=True)
class Failure:
    stage: str
    code: str
    error_type: str
    recoverable: bool = True

    def __post_init__(self):
        for value in (self.stage, self.code, self.error_type):
            identifier(value)
        if type(self.recoverable) is not bool:
            raise ValueError('failure recoverability must be explicit')


class StageFailure(RuntimeError):
    """A failed stage with a bounded diagnostic; never a fabricated result."""
    def __init__(self, failure, record=None):
        self.failure = failure
        self.record = record
        super().__init__(failure.stage + ': ' + failure.code)
