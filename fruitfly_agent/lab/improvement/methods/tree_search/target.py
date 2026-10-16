"""The tree-search method owns its I policy artifact and validation."""
from fruitfly_agent.lab.algorithms.targets import TargetSnapshot, TargetBinding
from .policy import ExplorationPolicy

POLICY_TARGET = 'tree-search.exploration-policy'


class PolicyTarget:
    adoption_roles = frozenset({'I'})

    def __init__(self, text, execution_target):
        ExplorationPolicy.parse(text)
        self.text, self.execution_target = text, execution_target

    def snapshot(self):
        return TargetSnapshot(POLICY_TARGET, self.text, TargetBinding('artifact', POLICY_TARGET),
                              schema='exploration-policy-v1', role='I')

    def validate(self, text):
        ExplorationPolicy.parse(text)

    def prepare_trial(self, config, text):
        raise ValueError('exploration policies require search trials, not task-prompt projection')
