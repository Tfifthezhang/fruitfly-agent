"""Independent next-seed policies. They cannot choose the reported final result."""
from dataclasses import dataclass
from typing import Any, Callable

from fruitfly_agent.improvement.contracts.search import ExplorationDecision
from fruitfly_agent.improvement.contracts.assessment import AssessmentUnavailable


@dataclass(frozen=True)
class ExplorationSettings:
    policy: str = 'incumbent'

    def __post_init__(self):
        if not isinstance(self.policy, str) or not self.policy:
            raise ValueError('exploration policy must be a registered ID')


from fruitfly_agent.lab.improvement.strategies.incumbent import IncumbentExploration


class ProcessGuidedExploration:
    process_guided = True
    async def choose(self, task, records, incumbent, assessment):
        try:
            return await assessment.compare(task, records, incumbent)
        except AssessmentUnavailable as exc:
            return ExplorationDecision(incumbent.run_id,
                'Process comparison unavailable; retain incumbent: ' + str(exc), policy_id='process-guided')


@dataclass(frozen=True)
class ExplorationDefinition:
    policy_id: str
    implementation_id: str
    factory: Callable[[], Any]
    requires_comparison: bool = False


class ExplorationRegistry:
    def __init__(self, definitions=()):
        self.entries = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition):
        from fruitfly_agent.improvement.contracts.validation import identifier
        identifier(definition.policy_id)
        identifier(definition.implementation_id)
        if definition.policy_id in self.entries or not callable(definition.factory):
            raise ValueError('invalid or duplicate exploration policy')
        self.entries[definition.policy_id] = definition

    def get(self, name):
        try:
            return self.entries[name]
        except KeyError as exc:
            raise ValueError('unknown exploration policy: ' + str(name)) from exc

    def create(self, name, *, own=lambda value: value):
        result = own(self.get(name).factory())
        if not callable(getattr(result, 'choose', None)):
            raise ValueError('exploration policy must implement choose')
        return result


def builtin_explorations():
    return ExplorationRegistry((ExplorationDefinition('incumbent', 'incumbent-seed-v1', IncumbentExploration),
        ExplorationDefinition('process-guided', 'process-seed-v1', ProcessGuidedExploration, True)))


def validate_exploration(exploration, explorations):
    explorations.get(exploration.policy)
