"""Discover strategies without constructing models or running tasks."""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SearchSchedule:
    references: int
    rounds: int
    missions: tuple[tuple[str, int], ...]
    compositions: int = 0

    def __post_init__(self):
        if any(type(v) is not int or v < 1 for v in (self.references, self.rounds)):
            raise ValueError('a search needs references and rounds')
        if type(self.compositions) is not int or self.compositions < 0 or not self.missions:
            raise ValueError('invalid search schedule')


@dataclass(frozen=True)
class StrategyDefinition:
    strategy_id: str
    implementation_id: str
    label: str
    schedule: Callable
    validate_options: Callable | None = None


class StrategyRegistry:
    def __init__(self, definitions=()):
        self.entries = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition):
        if definition.strategy_id in self.entries:
            raise ValueError('duplicate search strategy')
        self.entries[definition.strategy_id] = definition

    def get(self, strategy_id):
        try:
            return self.entries[strategy_id]
        except KeyError as exc:
            raise ValueError('unknown search strategy: ' + strategy_id) from exc

    def definitions(self):
        return tuple(self.entries.values())


def builtin_strategies():
    from .simple import definition as simple
    from .harness2 import definition as harness2
    return StrategyRegistry((simple(), harness2()))
