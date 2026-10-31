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


