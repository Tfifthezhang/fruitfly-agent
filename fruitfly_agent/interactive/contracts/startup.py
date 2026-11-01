"""Offline startup presentation and explicit launch choices."""
from dataclasses import dataclass
from typing import Literal


StartupAction = Literal['start', 'configure', 'exit']


@dataclass(frozen=True)
class StartupSnapshot:
    model: str
    environment: str
    session: str
    ready: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConfigurationEditResult:
    """A completed offline edit; saving never implies starting resources."""

    saved: bool = False
