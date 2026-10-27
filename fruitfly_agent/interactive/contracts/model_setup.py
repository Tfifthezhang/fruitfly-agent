"""Optional host service for adding models without exposing credentials in views."""

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from fruitfly_agent.interactive.contracts.configuration import (
    ConfigurationActionResult,
    ConfigurationParameter,
)


@dataclass(frozen=True)
class ModelSetupOption:
    option_id: str
    label: str
    description: str
    fields: tuple[ConfigurationParameter, ...]
    group: str


class ModelSetupService(Protocol):
    def options(self) -> tuple[ModelSetupOption, ...]: ...
    def field(self, option_id: str, name: str, values: Mapping[str, str]) -> ConfigurationParameter: ...
    def defaults(self, option_id: str, values: Mapping[str, str]) -> Mapping[str, Any]: ...
    def stage(self, option_id: str, values: Mapping[str, str], secret: str) -> ConfigurationActionResult: ...
    def credential_status(self, model_profile: str) -> str: ...
    def stage_credential(self, model_profile: str, secret: str) -> ConfigurationActionResult: ...
