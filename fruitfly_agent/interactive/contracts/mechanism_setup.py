"""Optional generic mechanism forms with hidden credential inputs."""
from dataclasses import dataclass
from typing import Mapping, Protocol

from .configuration import ConfigurationActionResult, ConfigurationParameter


@dataclass(frozen=True)
class ConfigurationCredential:
    parameter: str
    label: str
    description: str
    available: bool = False


@dataclass(frozen=True)
class ConfigurationSetup:
    mechanism_id: str
    label: str
    fields: tuple[ConfigurationParameter, ...]
    credentials: tuple[ConfigurationCredential, ...]
    guidance: str = ''


class MechanismSetupService(Protocol):
    def form(self, mechanism_id: str) -> ConfigurationSetup: ...
    def ready(self, mechanism_id: str) -> bool: ...
    def validate_field(self, mechanism_id: str, name: str, value: str) -> None: ...
    def validate_credential(self, mechanism_id: str, name: str, value: str) -> None: ...
    def stage(self, mechanism_id: str, values: Mapping[str, str], secrets: Mapping[str, str]) -> ConfigurationActionResult: ...
