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

    @property
    def legacy_models(self) -> Path:
        return self.root / "models.yaml"

    @property
    def legacy_secrets(self) -> Path:
        return self.root / ".env"

    def model_catalog(self) -> Path | None:
        return next((path for path in (self.models, self.legacy_models) if path.is_file()), None)

    def secret_file(self) -> Path:
        # Keep the destination symlink visible to writers so they can reject it.
        if self.secrets.exists() or self.secrets.is_symlink():
            return self.secrets
        if self.legacy_secrets.is_file() or self.legacy_secrets.is_symlink():
            return self.legacy_secrets
        return self.secrets

    def notices(self) -> tuple[str, ...]:
        notices = []
        if self.models.is_file() and self.legacy_models.is_file():
            notices.append("Both model catalogs exist: discovery uses .fruitfly/models.yaml; saved catalog paths take precedence.")
        if self.secrets.is_file() and self.legacy_secrets.is_file():
            notices.append("Both secret files exist: using .fruitfly/secrets.env; the workspace .env is not merged.")
        return tuple(notices)
