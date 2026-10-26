"""Generic execution registration and borrowed construction capabilities."""
from dataclasses import dataclass
from typing import Any

from ..contracts.experiments import ExecutionDefinition


@dataclass
class ExecutionContext:
    workspace: Any
    artifacts: Any
    components: Any
    tasks: Any
    config: Any
    editor_config: Any
    experience: tuple = ()
    plan: Any = None
    services: Any = None
    runner_factory: Any = None
    measurements: Any = None
    verifier: Any = None
    claim_verification: Any = None
    remaining_verification: Any = None
    assessor_config: Any = None
    completed_assessment_factory: Any = None
    exploration_factory: Any = None
    save_record: Any = None
    component_ids: tuple[str, ...] = ()
    generator_definitions: tuple = ()
    system_settings: Any = None


class ExecutionRegistry:
    def __init__(self, definitions=()):
        self.entries = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: ExecutionDefinition):
        if definition.execution_id in self.entries:
            raise ValueError('duplicate execution definition')
        self.entries[definition.execution_id] = definition

    def definitions(self):
        return tuple(self.entries.values())

    def get(self, execution_id):
        try:
            return self.entries[execution_id]
        except KeyError as exc:
            raise ValueError('unknown execution definition: ' + execution_id) from exc


def builtin_executions():
    from .files import definition
    from ..improver.registration import definition as improver_definition
    return ExecutionRegistry((definition(), improver_definition()))
