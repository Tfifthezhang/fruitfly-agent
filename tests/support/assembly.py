"""Explicit model catalog and Provider assembly fixture."""
from __future__ import annotations
from pathlib import Path
from unittest.mock import Mock
from fruitfly_agent.run import build_runtime
from tests.support.faux_provider import FauxProvider
from tests.support.run import _write_catalog

class AssemblyWorkspace:
    def __init__(self, root) -> None:
        self.root = Path(root)
        self.model_path = self.root / "models.yaml"
        _write_catalog(self.model_path, {"offline": "offline-model"})
        self.registry = Mock()
        self.registry.create.side_effect = lambda *_: FauxProvider()

    def assemble(self, profile, session, *, catalog, **kwargs):
        return build_runtime(
            profile, session=session, catalog=catalog, cwd=self.root,
            provider_registry=self.registry, environment=kwargs.pop("environment", {}),
            config_path=kwargs.pop("config_path", self.root / "config.yaml"), **kwargs,
        )
