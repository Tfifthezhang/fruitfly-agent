"""Serializable mechanism choices; Catalog owns their semantic resolution."""
from dataclasses import dataclass, field
from typing import Any, Mapping
import re

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

@dataclass(frozen=True)
class MechanismSelection:
    mechanism_id: str
    enabled: bool = True
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.mechanism_id):
            raise ValueError("selection mechanism_id must be a stable identifier")
        if not isinstance(self.enabled, bool):
            raise ValueError("selection enabled must be a boolean")
        if not isinstance(self.parameters, Mapping):
            raise ValueError("selection parameters must be a mapping")
        object.__setattr__(self, "parameters", dict(self.parameters))

    def to_dict(self) -> dict[str, Any]:
        values = {
            name: list(value) if isinstance(value, tuple) else value
            for name, value in self.parameters.items()
        }
        return {"id": self.mechanism_id, "enabled": self.enabled, "parameters": values}

