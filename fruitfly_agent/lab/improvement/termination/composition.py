"""Deterministic composition and explicit policy registration."""
from fruitfly_agent.improvement.contracts.stopping import StopDecision, stop_reason
from dataclasses import asdict, is_dataclass
from fruitfly_agent.improvement.contracts.versions import canonical_json


from fruitfly_agent.improvement.contracts.stopping import policy_spec


class AnyOf:
    def __init__(self, *policies):
        if not policies: raise ValueError('declare stopping conditions')
        self.policies = policies
    def decide(self, state):
        for policy in self.policies:
            decision = policy.decide(state)
            if decision is not None: return decision
        return None


class AllOf(AnyOf):
    def decide(self, state):
        decisions = [p.decide(state) for p in self.policies]
        if any(d is None for d in decisions): return None
        return StopDecision('all_of:' + ','.join(stop_reason(d) for d in decisions),
            tuple(v for d in decisions if isinstance(d, StopDecision) for v in d.evidence_ids))


class StopRegistry:
    def __init__(self): self.factories = {}
    def register(self, name, factory):
        if not name or name in self.factories or not callable(factory):
            raise ValueError('invalid stop policy registration')
        self.factories[name] = factory
    def create(self, name, **parameters):
        if name not in self.factories: raise ValueError('unknown stop policy: ' + name)
        return self.factories[name](**parameters)
