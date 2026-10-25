"""Independent settings for completed-execution assessment; no model construction."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ProcessAssessmentSettings:
    assessors: tuple[str, ...] = ()
    max_model_calls: int = 16
    timeout_seconds: float = 120
    required: bool = False

    def __post_init__(self):
        object.__setattr__(self, 'assessors', tuple(self.assessors))
        if len(set(self.assessors)) != len(self.assessors) or any(
                not isinstance(v, str) or not v.strip() for v in self.assessors):
            raise ValueError('process assessors must be distinct registered IDs')
        if type(self.max_model_calls) is not int or not 0 <= self.max_model_calls <= 10000:
            raise ValueError('invalid process-assessment model allowance')
        if (isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float))
                or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0):
            raise ValueError('process-assessment timeout must be finite and positive')
        if type(self.required) is not bool:
            raise ValueError('process-assessment requirement must be boolean')
        if self.required and not self.assessors:
            raise ValueError('required process assessment needs an assessor')
