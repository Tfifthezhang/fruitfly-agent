"""Independent assessor discovery; registration performs no model work."""
from dataclasses import dataclass
from typing import Any, Callable
from fruitfly_agent.improvement.contracts.validation import identifier


class AssessorRegistry:
    def __init__(self): self.factories = {}

    def register(self, name, factory):
        identifier(name)
        if name in self.factories or not callable(factory):
            raise ValueError('duplicate or invalid assessor registration')
        self.factories[name] = factory

    def definitions(self): return tuple(sorted(self.factories))

    def create(self, name, **parameters):
        if name not in self.factories: raise ValueError('unknown assessor: ' + name)
        return self.factories[name](**parameters)


@dataclass(frozen=True)
class CompletedAssessorDefinition:
    assessor_id: str
    implementation_id: str
    factory: Callable[[Any], Any]
    uses_model: bool = False
    comparison: bool = False


class CompletedAssessorRegistry:
    def __init__(self, definitions=()):
        self.entries = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition):
        identifier(definition.assessor_id)
        identifier(definition.implementation_id)
        if definition.assessor_id in self.entries or not callable(definition.factory):
            raise ValueError('invalid or duplicate completed assessor')
        self.entries[definition.assessor_id] = definition

    def get(self, name):
        try:
            return self.entries[name]
        except KeyError as exc:
            raise ValueError('unknown completed assessor: ' + str(name)) from exc

    def definitions(self):
        return tuple(self.entries.values())

    def create(self, name, service, *, own=lambda value: value):
        definition = self.get(name)
        result = own(definition.factory(service))
        if (result.assessor_id != name or not callable(getattr(result, 'assess', None))
                or definition.comparison and not callable(getattr(result, 'compare', None))):
            raise ValueError('completed assessor identity mismatch')
        return result


def builtin_completed_assessors():
    from .completed_assessors import CompletedFactsAssessor, CompletedModelAssessor
    return CompletedAssessorRegistry((
        CompletedAssessorDefinition('execution-facts-v1', 'completed-facts-v1', CompletedFactsAssessor),
        CompletedAssessorDefinition('completed-model-v1', 'completed-model-v1', CompletedModelAssessor, True, True)))
