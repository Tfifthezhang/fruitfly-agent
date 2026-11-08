"""Generic execution registration and borrowed construction capabilities."""
from dataclasses import dataclass
from typing import Any

from fruitfly_agent.improvement.contracts.experiments import ExecutionDefinition


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
    save_record: Any = None
    component_ids: tuple[str, ...] = ()
    generator_definitions: tuple = ()
    system_settings: Any = None
    hooks_factory: Any = None
    delivery_backend: Any = None
    evidence_settings: Any = None
    resource_factories: Any = None
    organizer_factory: Any = None
    organizer_config: Any = None


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
    from .tasks import definition
    from fruitfly_agent.lab.context_manager.augmentation.memory.improvement import execution_definitions
    return ExecutionRegistry((definition(), *execution_definitions()))
