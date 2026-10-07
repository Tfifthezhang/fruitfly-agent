"""Optional host service for adding models without exposing credentials in views."""

from dataclasses import dataclass
from typing import Mapping, Protocol

from .configuration import ConfigurationActionResult, ConfigurationParameter


@dataclass(frozen=True)
class ModelSetupOption:
    option_id: str
    label: str
    description: str
    fields: tuple[ConfigurationParameter, ...]


class ModelSetupService(Protocol):
    def options(self) -> tuple[ModelSetupOption, ...]: ...
    def stage(self, option_id: str, values: Mapping[str, str], secret: str) -> ConfigurationActionResult: ...
    def credential_status(self, model_profile: str) -> str: ...
    def stage_credential(self, model_profile: str, secret: str) -> ConfigurationActionResult: ...
