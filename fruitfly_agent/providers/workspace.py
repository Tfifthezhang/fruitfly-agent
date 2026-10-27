"""Workspace model and secret paths shared by runtime and external consumers."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path

    @property
    def models(self) -> Path:
        return self.root / ".fruitfly/models.yaml"

    @property
    def secrets(self) -> Path:
        return self.root / ".fruitfly/secrets.env"

    def model_catalog(self) -> Path | None:
        return self.models if self.models.is_file() else None

    def secret_file(self) -> Path:
        return self.secrets
