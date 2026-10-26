"""Frontend-independent approval of an external service's startup plan."""
from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass(frozen=True)
class ToolServiceStartPlan:
    name: str
    command: str
    arguments: tuple[str, ...]
    working_directory: str
    environment_names: tuple[str, ...]
    location: str = 'Local host'


ToolServiceStartupApproval = Callable[[ToolServiceStartPlan], Awaitable[bool]]
