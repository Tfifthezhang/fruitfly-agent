"""Public, non-secret execution metadata published by environment installers."""
from dataclasses import dataclass


EXECUTION_ENVIRONMENT_COMPONENT = "execution-environment-description"


@dataclass(frozen=True)
class ExecutionEnvironmentDescription:
    """Describe installed file/Bash execution, without transport or credentials."""

    label: str
    working_directory: str
    server: str = ""
