"""Renderer-neutral configuration views for a new-session-only editor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ConfigurationParameter:
    name: str
    label: str
    description: str
    kind: str
    value: Any
    choices: tuple[Any, ...] = ()
    advanced: bool = False
    minimum: float | None = None
    maximum: float | None = None
    nullable: bool = False


@dataclass(frozen=True)
class ConfigurationMechanism:
    mechanism_id: str
    category: str
    label: str
    description: str
    enabled: bool
    activation: str
    layer: str = "online"
    family: str = "context"
    context_phase: str | None = None
    display_section: str | None = None
    visible: bool = True
    parameters: tuple[ConfigurationParameter, ...] = ()
    effects: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    exclusive_group: str | None = None
    selection_group: str | None = None
    selection_group_label: str | None = None
    selection_group_allow_disabled: bool = True


@dataclass(frozen=True)
class ConfigurationSelectionGroup:
    group_id: str
    label: str
    category: str
    section: str | None
    option_ids: tuple[str, ...]
    selected_id: str | None
    allow_disabled: bool = True


@dataclass(frozen=True)
class ConfigurationSnapshot:
    """Non-secret, renderer-neutral choices for a future Agent session."""

    config_path: str
    selected_profile: str
    profiles: tuple[str, ...]
    model_catalog: str
    model_profile: str | None
    model_profiles: tuple[str, ...]
    mechanisms: tuple[ConfigurationMechanism, ...]
    selection_groups: tuple[ConfigurationSelectionGroup, ...] = ()
    prompt_reference: str = "assistant-default"
    prompt_label: str = "Assistant default"
    prompt_options: tuple[str, ...] = ()
    ready: bool = True
    changed: bool = False
    warnings: tuple[str, ...] = ()
    prompt_option_labels: tuple[tuple[str, str], ...] = ()
    # Group ID, display label, opaque references, collapsible selector.
    prompt_option_groups: tuple[tuple[str, str, tuple[str, ...], bool], ...] = ()


@dataclass(frozen=True)
class ConfigurationActionResult:
    message: str
    changed: bool = False
    saved: bool = False


@dataclass(frozen=True)
class ConfigurationLaunchResult:
    """Outcome of a Provider-free startup configuration view."""

    start: bool
    saved: bool = False
    version_tokens: tuple[str, ...] = ()
    remember_tokens: tuple[str, ...] = ()


@dataclass(frozen=True)
class StartupVersion:
    token: str
    target: str
    label: str
    detail: str = ''
    current: bool = False
    preview_text: str = ''


class StartupVersions(Protocol):
    """Optional injected startup choices; tokens are opaque to the terminal."""
    def versions(self, snapshot: ConfigurationSnapshot) -> tuple[StartupVersion, ...]: ...


class ConfigurationController(Protocol):
    """Injected by the composition root; Interactive never imports Lab."""

    def snapshot(self) -> ConfigurationSnapshot: ...

    def select_profile(self, profile_id: str) -> ConfigurationActionResult: ...

    def select_model_catalog(self, path: str) -> ConfigurationActionResult: ...

    def select_model(self, model_profile: str) -> ConfigurationActionResult: ...

    def select_prompt(self, reference: str) -> ConfigurationActionResult: ...

    def preview_prompt(self, reference: str) -> tuple[str, str, str]: ...

    def set_mechanism(
        self, mechanism_id: str, *, enabled: bool
    ) -> ConfigurationActionResult: ...

    def set_parameter(
        self, mechanism_id: str, name: str, value: str
    ) -> ConfigurationActionResult: ...

    def select_algorithm(self, group_id: str, option_id: str | None) -> ConfigurationActionResult: ...

    def save(self) -> ConfigurationActionResult: ...

    def reset(self) -> ConfigurationActionResult: ...


__all__ = [
    "ConfigurationParameter",
    "ConfigurationMechanism",
    "ConfigurationSelectionGroup",
    "ConfigurationSnapshot",
    "ConfigurationActionResult",
    "ConfigurationLaunchResult",
    "ConfigurationController",
    "StartupVersion",
    "StartupVersions",
]
