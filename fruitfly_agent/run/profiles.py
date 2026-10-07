"""Harness-profile discovery and the next-session configuration controller."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fruitfly_agent.interactive import (
    ConfigurationActionResult,
    ConfigurationSnapshot,
)
from fruitfly_agent.lab.catalog import (
    LabCatalog,
    MechanismSelection,
)
from fruitfly_agent.run.configuration import (
    HarnessConfig,
    HarnessProfile,
    save_harness_config,
)
from fruitfly_agent.providers.registry import load_model_specs
from .artifacts import DataArtifactStore
from .configuration_views import mechanism_views, prompt_choices, display_group
from .model_selection import (
    HarnessSelection, resolve_harness_selection, default_model_catalog_path,
    model_catalog_path, resolve_profile_models,
)
from .model_setup import RunModelSetup


class RunConfigurationController:
    """Edit and save a profile without mutating the active Agent session."""

    def __init__(
        self,
        selection: HarnessSelection,
        catalog: LabCatalog,
        artifact_store: DataArtifactStore | None = None,
    ) -> None:
        self._original = selection.config
        self._draft = selection.config
        self._selected = selection.profile.profile_id
        self._original_selected = selection.profile.profile_id
        self._path = selection.config_path
        self._catalog = catalog
        self._artifact_store = artifact_store or DataArtifactStore(
            self._path.parent / "artifacts"
        )
        self._persisted = selection.persisted
        self.model_setup: RunModelSetup | None = None

    def _models(self, profile: HarnessProfile):
        return self.model_setup.models(profile) if self.model_setup is not None else load_model_specs(model_catalog_path(profile, self._path))

    def snapshot(self) -> ConfigurationSnapshot:
        from .assembly import resolve_base_prompt
        profile = self._draft.select(self._selected)
        warnings: list[str] = []
        ready = True
        try:
            models = self._models(profile)
            selected_model = profile.model_profile
            if selected_model is None and len(models) == 1:
                selected_model = next(iter(models))
            elif selected_model is None:
                warnings.append("select one model profile before saving")
                ready = False
            elif selected_model not in models:
                warnings.append(f"unknown model profile {selected_model!r}")
                ready = False
        except (OSError, TypeError, ValueError) as exc:
            models = {}
            selected_model = profile.model_profile
            warnings.append(str(exc))
            ready = False
        try:
            self._catalog.resolve(profile.mechanisms)
        except (TypeError, ValueError) as exc:
            warnings.append(str(exc))
            ready = False
        try:
            _, prompt_identity = resolve_base_prompt(profile.prompt, self._artifact_store)
            prompt_label = prompt_identity["label"]
        except (OSError, TypeError, ValueError) as exc:
            warnings.append(str(exc))
            prompt_label = profile.prompt
            ready = False
        prompt_options, prompt_labels, prompt_groups = prompt_choices(profile, self._artifact_store, self._path)
        mechanisms, selection_groups = mechanism_views(profile, self._catalog, warnings)
        return ConfigurationSnapshot(
            config_path=str(self._path),
            selected_profile=self._selected,
            profiles=tuple(sorted(self._draft.profiles)),
            model_catalog=profile.model_catalog,
            model_profile=selected_model,
            model_profiles=tuple(sorted(models)),
            mechanisms=tuple(mechanisms),
            selection_groups=tuple(selection_groups),
            prompt_reference=profile.prompt,
            prompt_label=prompt_label,
            prompt_options=prompt_options,
            prompt_option_labels=prompt_labels,
            prompt_option_groups=prompt_groups,
            ready=ready,
            changed=self._is_changed(),
            warnings=tuple(warnings),
        )

    def select_profile(self, profile_id: str) -> ConfigurationActionResult:
        self._draft.select(profile_id)
        self._selected = profile_id
        return _changed(
            f"staged profile {profile_id!r}; save and start a new session"
        )

    def select_model(self, model_profile: str) -> ConfigurationActionResult:
        profile = self._draft.select(self._selected)
        models = self._models(profile)
        if model_profile not in models:
            available = ", ".join(sorted(models)) or "none"
            raise ValueError(
                f"unknown model profile {model_profile!r} (available: {available})"
            )
        self._replace_profile(replace(profile, model_profile=model_profile))
        return _changed(
            f"staged model {model_profile!r}; save and start a new session"
        )

    def select_prompt(self, reference: str) -> ConfigurationActionResult:
        from .assembly import resolve_base_prompt
        resolve_base_prompt(reference, self._artifact_store)
        profile = self._draft.select(self._selected)
        self._replace_profile(replace(profile, prompt=reference))
        return _changed(f"staged base prompt {reference!r}; save and start a new session")

    def bind_target(self, kind: str, key: str, reference: str):
        """Persist a declared host binding; target-specific validation lives in Lab."""
        if kind == "prompt":
            return self.select_prompt(reference)
        if kind != "artifact":
            raise ValueError("unsupported target binding kind")
        profile = self._draft.select(self._selected)
        slots = {slot for item in self._catalog.resolve(profile.mechanisms) for slot in item.definition.artifact_slots}
        if key not in slots:
            raise ValueError("target slot is not enabled")
        self._artifact_store.read_text(reference)
        bindings = dict(profile.artifact_bindings)
        bindings[key] = reference
        self._replace_profile(replace(profile, artifact_bindings=bindings))
        return _changed("staged target artifact; start a new session")

    def preview_prompt(self, reference: str) -> tuple[str, str, str]:
        from .assembly import resolve_base_prompt
        content, identity = resolve_base_prompt(reference, self._artifact_store)
        return dict(prompt_choices(self._draft.select(self._selected), self._artifact_store, self._path)[1]).get(reference, identity["label"]), identity["content_hash"], content

    def select_model_catalog(self, path: str) -> ConfigurationActionResult:
        value = path.strip()
        if not value:
            raise ValueError("model catalog path must not be empty")
        profile = self._draft.select(self._selected)
        candidate = replace(profile, model_catalog=value, model_profile=None)
        models = load_model_specs(model_catalog_path(candidate, self._path))
        selected = next(iter(models)) if len(models) == 1 else None
        self._replace_profile(replace(candidate, model_profile=selected))
        suffix = f" and selected {selected!r}" if selected is not None else ""
        return _changed(
            f"staged model catalog {value!r}{suffix}; "
            "save and start a new session"
        )

    def set_mechanism(
        self,
        mechanism_id: str,
        *,
        enabled: bool,
    ) -> ConfigurationActionResult:
        definition = self._catalog.get(mechanism_id)
        profile = self._draft.select(self._selected)
        selections = {
            item.mechanism_id: item for item in profile.mechanisms
        }
        changed_ids = {mechanism_id}
        if enabled:
            descriptor = definition.descriptor
            disabled = set(descriptor.conflicts)
            disabled.update(
                item.mechanism_id
                for item in self._catalog.descriptors()
                if mechanism_id in item.conflicts
            )
            if descriptor.exclusive_group is not None:
                disabled.update(
                    item.mechanism_id
                    for item in self._catalog.descriptors()
                    if item.exclusive_group == descriptor.exclusive_group
                    and item.mechanism_id != mechanism_id
                )
            for other_id in disabled:
                if other_id in selections:
                    selections[other_id] = replace(
                        selections[other_id],
                        enabled=False,
                    )
                    changed_ids.add(other_id)
            pending = list(self._catalog.capability_dependencies(mechanism_id, selections.values()))
            visited: set[str] = set()
            while pending:
                required_id = pending.pop()
                if required_id in visited:
                    continue
                visited.add(required_id)
                required = self._catalog.get(required_id).descriptor
                existing = selections.get(required_id)
                selections[required_id] = MechanismSelection(
                    required_id,
                    enabled=True,
                    parameters=(
                        existing.parameters
                        if existing is not None
                        else {item.name: item.default for item in required.parameters}
                    ),
                )
                changed_ids.add(required_id)
                pending.extend(self._catalog.capability_dependencies(required_id, selections.values()))
        else:
            dependency_map = {
                item.mechanism_id: self._catalog.capability_dependencies(item.mechanism_id, selections.values())
                for item in self._catalog.descriptors()
                if selections.get(item.mechanism_id, MechanismSelection(item.mechanism_id, False)).enabled
            }
            pending = [mechanism_id]
            visited = set()
            while pending:
                disabled_id = pending.pop()
                if disabled_id in visited:
                    continue
                visited.add(disabled_id)
                existing = selections.get(disabled_id)
                if existing is not None:
                    selections[disabled_id] = replace(existing, enabled=False)
                changed_ids.add(disabled_id)
                pending.extend(
                    item.mechanism_id
                    for item in self._catalog.descriptors()
                    if disabled_id in dependency_map.get(item.mechanism_id, ())
                    and selections.get(
                        item.mechanism_id,
                        MechanismSelection(item.mechanism_id, False),
                    ).enabled
                )
        existing = selections.get(mechanism_id)
        selections[mechanism_id] = MechanismSelection(
            mechanism_id,
            enabled=enabled,
            parameters=(
                existing.parameters
                if existing is not None
                else {
                    item.name: item.default
                    for item in definition.descriptor.parameters
                }
            ),
        )
        self._replace_profile(
            replace(profile, mechanisms=tuple(selections.values()))
        )
        action = "enabled" if enabled else "disabled"
        related = sorted(changed_ids - {mechanism_id})
        suffix = (
            f"; adjusted dependencies/conflicts: {', '.join(related)}"
            if related
            else ""
        )
        return _changed(
            f"staged {mechanism_id!r} {action}{suffix}; "
            "save and start a new session"
        )

    def select_algorithm(self, group_id: str, option_id: str | None) -> ConfigurationActionResult:
        """Apply one declared algorithm choice to the draft as an atomic operation."""
        members = [definition for definition in self._catalog.definitions()
                   if definition.selection_group == group_id]
        if not members:
            raise ValueError(f"unknown algorithm selection group {group_id!r}")
        member_ids = {item.descriptor.mechanism_id for item in members}
        if option_id is not None and option_id not in member_ids:
            raise ValueError(f"option {option_id!r} is not in selection group {group_id!r}")
        if option_id is None and not members[0].selection_group_allow_disabled:
            raise ValueError(f"selection group {group_id!r} cannot be disabled")
        profile = self._draft.select(self._selected)
        original_draft = self._draft
        try:
            selected = {item.mechanism_id: item for item in profile.mechanisms}
            if option_id is None:
                for mechanism_id in member_ids:
                    if selected.get(mechanism_id, MechanismSelection(mechanism_id, False)).enabled:
                        self.set_mechanism(mechanism_id, enabled=False)
            else:
                # Disable sibling choices in the candidate draft, then let the
                # ordinary mechanism controller install dependencies/conflicts.
                for mechanism_id in member_ids - {option_id}:
                    existing = selected.get(mechanism_id)
                    if existing is not None:
                        selected[mechanism_id] = replace(existing, enabled=False)
                self._replace_profile(replace(profile, mechanisms=tuple(selected.values())))
                self.set_mechanism(option_id, enabled=True)
            candidate = self._draft.select(self._selected)
            self._catalog.resolve(candidate.mechanisms)
        except BaseException:
            self._draft = original_draft
            raise
        return _changed(f"staged selection {option_id or 'disabled'} in {group_id}; save and start a new session")

    def set_parameter(
        self,
        mechanism_id: str,
        name: str,
        value: str,
    ) -> ConfigurationActionResult:
        definition = self._catalog.get(mechanism_id)
        descriptors = {
            item.name: item for item in definition.descriptor.parameters
        }
        try:
            parameter = descriptors[name]
        except KeyError as exc:
            available = ", ".join(sorted(descriptors)) or "none"
            raise ValueError(
                f"unknown parameter {name!r} for {mechanism_id!r} "
                f"(available: {available})"
            ) from exc
        parsed = parameter.parse(value)
        profile = self._draft.select(self._selected)
        selections = list(profile.mechanisms)
        index = next((i for i, item in enumerate(selections)
                      if item.mechanism_id == mechanism_id), len(selections))
        existing = selections[index] if index < len(selections) else None
        parameters = (dict(existing.parameters) if existing is not None else
                      {item.name: item.default for item in definition.descriptor.parameters})
        parameters[name] = parsed
        selection = MechanismSelection(
            mechanism_id, enabled=existing.enabled if existing is not None else False,
            parameters=parameters,
        )
        if existing is None:
            selections.append(selection)
        else:
            selections[index] = selection
        self._replace_profile(replace(profile, mechanisms=tuple(selections)))
        return _changed(
            f"staged {mechanism_id}.{name}={parsed!r}; "
            "save and start a new session"
        )

    def save(self) -> ConfigurationActionResult:
        from .assembly import resolve_base_prompt
        candidate = HarnessConfig(
            default_profile=self._selected,
            profiles=self._draft.profiles,
        )
        for profile in candidate.profiles.values():
            self._catalog.resolve(profile.mechanisms)
            if self.model_setup is None:
                resolve_profile_models(profile, self._path)
            else:
                models = self._models(profile)
                if profile.model_profile not in models and not (profile.model_profile is None and len(models) == 1):
                    raise ValueError("Select a valid model before saving")
            resolve_base_prompt(profile.prompt, self._artifact_store)
        if self.model_setup is not None and self.model_setup.changed:
            self.model_setup.persist(lambda: save_harness_config(self._path, candidate))
        else:
            save_harness_config(self._path, candidate)
        self._draft = candidate
        self._original = candidate
        self._original_selected = self._selected
        self._persisted = True
        return ConfigurationActionResult(
            message=(
                f"saved {self._path}; configuration is ready for a newly "
                "created session"
            ),
            saved=True,
        )

    def reset(self) -> ConfigurationActionResult:
        if self.model_setup is not None:
            self.model_setup.reset()
        self._draft = self._original
        self._selected = self._original_selected
        return ConfigurationActionResult(
            "discarded staged changes; current session was unchanged"
        )

    def _replace_profile(self, profile: HarnessProfile) -> None:
        profiles = dict(self._draft.profiles)
        profiles[profile.profile_id] = profile
        self._draft = HarnessConfig(
            default_profile=self._draft.default_profile,
            profiles=profiles,
        )

    def _is_changed(self) -> bool:
        return (
            not self._persisted
            or self._draft != self._original
            or self._selected != self._original_selected
            or (self.model_setup is not None and self.model_setup.changed)
        )


def _changed(message: str) -> ConfigurationActionResult:
    return ConfigurationActionResult(message, changed=True)



__all__ = [
    "HarnessSelection",
    "resolve_harness_selection",
    "default_model_catalog_path",
    "model_catalog_path",
    "resolve_profile_models",
    "RunConfigurationController",
    "display_group",
]
