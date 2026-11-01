"""Default fixed workflow over the independent Improvement runtime."""
from fruitfly_agent.improvement.workflow.controller import ImprovementWorkflow as RuntimeWorkflow
from ..termination.policies import BoundedStopPolicy
from ..assessment.measured import SelectionPolicy


class ImprovementWorkflow(RuntimeWorkflow):
    def __init__(self, **ports):
        for name, value in {'stop_policy': BoundedStopPolicy(), 'selection': SelectionPolicy()}.items():
            if ports.get(name) is None:
                ports[name] = value
        super().__init__(**ports)
