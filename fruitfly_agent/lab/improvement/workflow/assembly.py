"""Compose Lab mechanisms around the independent Improvement runtime."""
from fruitfly_agent.improvement.workflow.controller import ImprovementWorkflow as RuntimeWorkflow
from ..strategies import builtin_strategies
from ..strategies.incumbent import IncumbentExploration
from ..termination.policies import BoundedStopPolicy
from ..assessment.measured import SelectionPolicy


class ImprovementWorkflow(RuntimeWorkflow):
    def __init__(self, *, strategies=None, **ports):
        defaults = {'stop_policy': BoundedStopPolicy(), 'exploration': IncumbentExploration(),
                    'selection': SelectionPolicy()}
        for name, value in defaults.items():
            if ports.get(name) is None:
                ports[name] = value
        super().__init__(strategies=strategies if strategies is not None else builtin_strategies(), **ports)
