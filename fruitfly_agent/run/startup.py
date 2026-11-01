"""Offline startup projection; resource lifecycle remains in Application."""
from pathlib import Path

from fruitfly_agent.interactive.contracts.configuration import ConfigurationSnapshot
from fruitfly_agent.interactive.contracts.startup import StartupSnapshot
from fruitfly_agent.lab.catalog import LabCatalog, ExecutionEnvironmentDescription


def describe_startup(snapshot: ConfigurationSnapshot, *, catalog: LabCatalog,
                     workspace: Path, resume: bool, session: str | None) -> StartupSnapshot:
    environments: list[str] = []
    for mechanism in snapshot.mechanisms:
        if not mechanism.enabled or mechanism.family != 'environment':
            continue
        definition = catalog.get(mechanism.mechanism_id)
        description = definition.execution_description
        if description is None:
            environments.append(mechanism.label)
            continue
        try:
            value = description({p.name: p.value for p in mechanism.parameters}, workspace)
        except ValueError:
            environments.append(mechanism.label + ' · Configuration needs attention')
            continue
        if not isinstance(value, ExecutionEnvironmentDescription):
            raise TypeError('execution_description must return the public Lab view')
        environments.append(' · '.join(part for part in
            (value.label, value.server, value.working_directory) if part))
    return StartupSnapshot(snapshot.model_profile or 'Select a model',
        '; '.join(environments) or 'No execution environment selected',
        ('Resume · ' + (session or 'Latest non-empty session')) if resume else
            ('New session · ' + session if session else 'New session'),
        snapshot.ready, snapshot.warnings)
