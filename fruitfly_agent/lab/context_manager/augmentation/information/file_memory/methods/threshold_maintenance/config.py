"""Two trigger counters plus invocation bounds, independent of wall-clock delays."""
from dataclasses import dataclass


@dataclass(frozen=True)
class MaintenanceConfig:
    extract_after_user_chars: int = 8000
    consolidate_after_user_turns: int = 50
    max_input_chars: int = 64000
    max_output_tokens: int = 4096
    timeout_seconds: int = 120

    def __post_init__(self):
        for name, value in vars(self).items():
            if type(value) is not int or value < 1:
                raise ValueError('maintenance parameter must be a positive integer: ' + name)
