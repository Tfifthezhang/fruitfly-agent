"""Public configuration composition entry point with candidate-backed prompt views."""
from .configuration.controller import RunConfigurationController as ConfigurationController
from .configuration.resolution import (HarnessSelection, resolve_harness_selection,
    default_model_catalog_path, model_catalog_path, resolve_profile_models)
from .configuration.views import display_group
from .storage.artifacts import DataArtifactStore
from .storage.candidates import CandidateStore
from .adapters.configuration import candidate_prompt_choices


class RunConfigurationController(ConfigurationController):
    def __init__(self, selection, catalog, artifact_store=None):
        store = artifact_store or DataArtifactStore(selection.config_path.parent / "artifacts")
        candidates = CandidateStore(store.root.parent / "optimization/candidates", store)
        super().__init__(selection, catalog, store,
            prompt_choices_provider=lambda profile: candidate_prompt_choices(
                profile, read_text=store.read_text, records=candidates.list,
                config_path=selection.config_path))


__all__ = ["HarnessSelection", "resolve_harness_selection", "default_model_catalog_path",
           "model_catalog_path", "resolve_profile_models", "RunConfigurationController", "display_group"]
