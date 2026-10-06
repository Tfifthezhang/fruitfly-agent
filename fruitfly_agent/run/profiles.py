"""Harness-profile discovery and the next-session configuration controller."""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
from typing import Any, Mapping

from fruitfly_agent.interactive import (
    ConfigurationActionResult,
    ConfigurationMechanism,
    ConfigurationParameter,
    ConfigurationSelectionGroup,
    ConfigurationSnapshot,
)
from fruitfly_agent.lab.catalog import (
    LabCatalog,
    MechanismSelection,
)
from fruitfly_agent.run.configuration import (
    DEFAULT_HARNESS_CONFIG_NAME,
    HarnessConfig,
    HarnessProfile,
    load_harness_config,
    save_harness_config,
)
from fruitfly_agent.providers.registry import load_model_specs
from fruitfly_agent.providers.specs import ModelSpec
from fruitfly_agent.lab.base_prompt import builtins
from .artifacts import DataArtifactStore
from .optimization import CandidateStore


@dataclass(frozen=True)
class HarnessSelection:
    config: HarnessConfig
    profile: HarnessProfile
    config_path: Path
    persisted: bool


def resolve_harness_selection(
    *,
    cwd: Path,
    config_path: str | None,
    profile_id: str | None,
    environment: Mapping[str, str],
    catalog: LabCatalog,
    allow_incomplete: bool = False,
) -> HarnessSelection:
    """Load an explicit/default config or synthesize the documented baseline."""

    target = _resolve_config_path(cwd, config_path)
    if target.is_file():
        config = load_harness_config(target)
        profile = config.select(profile_id)
        return HarnessSelection(config, profile, target, True)
    if config_path is not None and not allow_incomplete:
        raise ValueError(f"harness config not found: {target}")
    if profile_id is not None:
        raise ValueError("--profile requires a harness config")

    model_catalog = default_model_catalog_path(cwd)
    if model_catalog is None:
        if allow_incomplete:
            return _incomplete_selection(
                target,
                catalog,
                _model_catalog_reference(cwd / "models.yaml", target),
            )
        raise ValueError("no models.yaml found; configure a model catalog")
    models = load_model_specs(model_catalog)
    selected_model = environment.get("FRUITFLY_MODEL_PROFILE")
    if selected_model is None:
        if len(models) != 1:
            if allow_incomplete:
                return _incomplete_selection(
                    target,
                    catalog,
                    _model_catalog_reference(model_catalog, target),
                )
            available = ", ".join(sorted(models)) or "none"
            raise ValueError(
                "model profile is ambiguous; configure .fruitfly/config.yaml or set "
                f"FRUITFLY_MODEL_PROFILE (available: {available})"
            )
        selected_model = next(iter(models))
    if selected_model not in models:
        available = ", ".join(sorted(models)) or "none"
        raise ValueError(
            f"unknown model profile {selected_model!r} (available: {available})"
        )
    profile = HarnessProfile(
        profile_id="default",
        model_catalog=_model_catalog_reference(model_catalog, target),
        model_profile=selected_model,
        mechanisms=catalog.default_selections(),
    )
    config = HarnessConfig(default_profile="default", profiles={"default": profile})
    return HarnessSelection(config, profile, target, False)


def default_model_catalog_path(cwd: Path) -> Path | None:
    candidates = (
        cwd / "models.yaml",
        Path(__file__).resolve().parents[2] / "models.yaml",
    )
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return candidate
    return None


def model_catalog_path(profile: HarnessProfile, config_path: Path) -> Path:
    path = Path(profile.model_catalog)
    if not path.is_absolute():
        path = config_path.parent / path
    return path.resolve()


def resolve_profile_models(
    profile: HarnessProfile,
    config_path: Path,
) -> tuple[dict[str, ModelSpec], str, ModelSpec]:
    path = model_catalog_path(profile, config_path)
    models = load_model_specs(path)
    selected = profile.model_profile
    if selected is None:
        if len(models) != 1:
            available = ", ".join(sorted(models)) or "none"
            raise ValueError(
                f"profile {profile.profile_id!r} model is ambiguous "
                f"(available: {available})"
            )
        selected = next(iter(models))
    try:
        spec = models[selected]
    except KeyError as exc:
        available = ", ".join(sorted(models)) or "none"
        raise ValueError(
            f"unknown model profile {selected!r} (available: {available})"
        ) from exc
    return models, selected, spec


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

    def snapshot(self) -> ConfigurationSnapshot:
        from .assembly import resolve_base_prompt
        profile = self._draft.select(self._selected)
        warnings: list[str] = []
        ready = True
        try:
            models = load_model_specs(model_catalog_path(profile, self._path))
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
        prompt_options, prompt_labels, prompt_groups = self._prompt_choices(profile)
        selections = {
            item.mechanism_id: item for item in profile.mechanisms
        }
        mechanisms: list[ConfigurationMechanism] = []
        for descriptor in sorted(
            self._catalog.descriptors(),
            key=lambda item: (
                display_group(item),
                _context_phase_order(item),
                item.install_order,
                item.mechanism_id,
            ),
        ):
            selection = selections.get(descriptor.mechanism_id)
            enabled = selection.enabled if selection is not None else False
            raw_parameters = selection.parameters if selection is not None else {}
            try:
                values = descriptor.normalize_parameters(raw_parameters)
            except ValueError as exc:
                warnings.append(str(exc))
                values = {
                    item.name: raw_parameters.get(item.name, item.default)
                    for item in descriptor.parameters
                }
            parameters = tuple(
                ConfigurationParameter(
                    name=item.name,
                    label=item.label,
                    description=item.description,
                    kind=item.kind,
                    value=values[item.name],
                    choices=item.choices,
                    advanced=item.advanced,
                    minimum=item.minimum,
                    maximum=item.maximum,
                    nullable=item.nullable,
                )
                for item in descriptor.parameters
            )
            mechanisms.append(
                ConfigurationMechanism(
                    mechanism_id=descriptor.mechanism_id,
                    category=display_group(descriptor),
                    label=descriptor.label,
                    description=descriptor.description,
                    enabled=enabled,
                    activation=descriptor.activation,
                    layer=descriptor.primary.layer,
                    family=descriptor.primary.family,
                    context_phase=descriptor.primary.context_phase,
                    display_section=_display_section(descriptor),
                    visible=self._catalog.get(descriptor.mechanism_id).visible,
                    parameters=parameters,
                    effects=_selection_effect_messages(
                        descriptor.mechanism_id,
                        descriptor.effects,
                        values,
                    ),
                    requires=tuple(sorted(descriptor.requires)),
                    conflicts=tuple(sorted(descriptor.conflicts)),
                    exclusive_group=descriptor.exclusive_group,
                    selection_group=self._catalog.get(descriptor.mechanism_id).selection_group,
                    selection_group_label=self._catalog.get(descriptor.mechanism_id).selection_group_label,
                    selection_group_allow_disabled=self._catalog.get(descriptor.mechanism_id).selection_group_allow_disabled,
                )
            )
        selection_groups = []
        grouped_definitions: dict[str, list] = {}
        for mechanism in mechanisms:
            if mechanism.selection_group is not None:
                grouped_definitions.setdefault(mechanism.selection_group, []).append(mechanism)
        for group_id, options in sorted(grouped_definitions.items()):
            enabled_options = [item.mechanism_id for item in options if item.enabled]
            selection_groups.append(ConfigurationSelectionGroup(
                group_id=group_id,
                label=options[0].selection_group_label or group_id,
                category=options[0].category,
                section=options[0].display_section,
                option_ids=tuple(item.mechanism_id for item in options),
                selected_id=enabled_options[0] if enabled_options else None,
                allow_disabled=options[0].selection_group_allow_disabled,
            ))
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

    def _prompt_choices(self, profile):
        options = {prompt.prompt_id: prompt.label for prompt in builtins()}
        builtin_ids = tuple(options)
        hashes = {prompt.content_hash for prompt in builtins()}
        store = CandidateStore(self._artifact_store.root.parent / 'optimization/candidates', self._artifact_store)
        seen = set()
        scope = (str(self._path.resolve()), profile.profile_id)
        try:
            records = store.list()
        except (OSError, ValueError, TypeError):
            records = ()
        for record in records:
            if (record.config_path, record.profile_id) != scope or record.target != 'base_prompt':
                continue
            task = record.task_pack_id
            if task in seen:
                continue
            seen.add(task)
            if record.status in {'rejected', 'stale'}:
                continue
            try:
                self._artifact_store.read_text(record.artifact_id)
            except (OSError, ValueError):
                continue
            if record.artifact_id in hashes:
                continue
            hashes.add(record.artifact_id)
            name = record.task_pack_name or task or 'Unattributed task'
            options[record.artifact_id] = f'{name} · {record.algorithm.upper()} optimized · {record.status}'
        if profile.prompt not in options:
            label = 'Current selected prompt'
            selected = next((r for r in records if (r.config_path, r.profile_id) == scope
                             and r.target == 'base_prompt' and r.artifact_id == profile.prompt), None)
            if selected:
                label = f'{selected.task_pack_name or selected.task_pack_id or "Unattributed task"} · {selected.algorithm.upper()} optimized · current'
            options[profile.prompt] = label
        adapted_ids = tuple(ref for ref in options if ref not in builtin_ids)
        groups = (("builtin", "Built-in prompts", builtin_ids, False),
                  ("adapted", "Task / scenario adapted prompts", adapted_ids, True))
        return tuple(options), tuple(options.items()), groups

    def select_profile(self, profile_id: str) -> ConfigurationActionResult:
        self._draft.select(profile_id)
        self._selected = profile_id
        return _changed(
            f"staged profile {profile_id!r}; save and start a new session"
        )

    def select_model(self, model_profile: str) -> ConfigurationActionResult:
        profile = self._draft.select(self._selected)
        models = load_model_specs(model_catalog_path(profile, self._path))
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
        return dict(self._prompt_choices(self._draft.select(self._selected))[1]).get(reference, identity["label"]), identity["content_hash"], content

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
        for index, selection in enumerate(selections):
            if selection.mechanism_id != mechanism_id:
                continue
            parameters = dict(selection.parameters)
            parameters[name] = parsed
            selections[index] = MechanismSelection(
                mechanism_id,
                enabled=selection.enabled,
                parameters=parameters,
            )
            break
        else:
            parameters = {
                item.name: item.default
                for item in definition.descriptor.parameters
            }
            parameters[name] = parsed
            selections.append(
                MechanismSelection(
                    mechanism_id,
                    enabled=False,
                    parameters=parameters,
                )
            )
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
            resolve_profile_models(profile, self._path)
            resolve_base_prompt(profile.prompt, self._artifact_store)
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
        )


def _resolve_config_path(cwd: Path, value: str | None) -> Path:
    if value is None:
        return (cwd / DEFAULT_HARNESS_CONFIG_NAME).resolve()
    path = Path(value)
    return path.resolve() if path.is_absolute() else (cwd / path).resolve()


def _incomplete_selection(
    target: Path,
    catalog: LabCatalog,
    model_catalog: str,
) -> HarnessSelection:
    profile = HarnessProfile(
        profile_id="default",
        model_catalog=model_catalog,
        model_profile=None,
        mechanisms=catalog.default_selections(),
    )
    config = HarnessConfig(default_profile="default", profiles={"default": profile})
    return HarnessSelection(config, profile, target, False)


def _model_catalog_reference(model_catalog: Path, config_path: Path) -> str:
    return os.path.relpath(
        model_catalog.resolve(),
        start=config_path.parent.resolve(),
    )


def _changed(message: str) -> ConfigurationActionResult:
    return ConfigurationActionResult(message, changed=True)


def _effect_messages(effects) -> tuple[str, ...]:
    rows = []
    if effects.uses_provider:
        rows.append("uses an auxiliary Provider")
    if effects.uses_network:
        rows.append("may access the network and incur cost")
    if effects.writes_files:
        rows.append("writes persistent files or session metadata")
    if effects.tools:
        rows.append("adds tools: " + ", ".join(effects.tools))
    if effects.lifecycle_hooks:
        rows.append("hooks: " + ", ".join(effects.lifecycle_hooks))
    if effects.cost_notice:
        rows.append(effects.cost_notice)
    return tuple(rows)


def _selection_effect_messages(
    mechanism_id: str,
    effects,
    parameters: Mapping[str, Any],
) -> tuple[str, ...]:
    """Describe the configured variant's real runtime effects."""

    return _effect_messages(effects)


def _display_section(descriptor) -> str | None:
    contribution = descriptor.primary
    if contribution.family != "context":
        return None
    if contribution.context_phase is not None:
        return contribution.context_phase
    if contribution.layer == "capability":
        return "augmentation"
    return None


def _context_phase_order(descriptor) -> int:
    phase = _display_section(descriptor)
    return {
        "augmentation": 0,
        "externalization": 1,
        "reduction": 2,
        None: 4,
    }[phase]


def display_group(descriptor) -> str:
    """Project Core mechanism coordinates into the current application menu."""
    contribution = descriptor.primary
    if contribution.layer == "optimization":
        return "optimization"
    if contribution.family == "context":
        return "context-manager"
    return contribution.family


__all__ = [
    "HarnessSelection",
    "resolve_harness_selection",
    "default_model_catalog_path",
    "model_catalog_path",
    "resolve_profile_models",
    "RunConfigurationController",
    "display_group",
]
