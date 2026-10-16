"""Bounded declarative policies see only the currently revealed search prefix."""
from dataclasses import dataclass, asdict
import json
import math


@dataclass(frozen=True)
class ExplorationPolicy:
    width: int = 1
    root_every: int = 1
    ranking: str = 'best'
    stop_fraction: float = 1.0

    def __post_init__(self):
        if type(self.width) is not int or not 1 <= self.width <= 16:
            raise ValueError('policy width must be 1–16')
        if type(self.root_every) is not int or not 1 <= self.root_every <= 100:
            raise ValueError('policy root_every must be 1–100')
        if self.ranking not in {'best', 'oldest', 'deepest'}:
            raise ValueError('unknown policy ranking')
        if isinstance(self.stop_fraction, bool) or not isinstance(self.stop_fraction, (int, float)) or not .05 <= self.stop_fraction <= 1:
            raise ValueError('policy stop_fraction must be .05–1')

    def serialize(self):
        return json.dumps(asdict(self), sort_keys=True, separators=(',', ':'))

    @classmethod
    def parse(cls, text):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate policy field')
                result[key] = value
            return result
        value = json.loads(text, object_pairs_hook=unique)
        if not isinstance(value, dict) or set(value) != set(asdict(cls())):
            raise ValueError('policy needs exactly width, root_every, ranking and stop_fraction')
        return cls(**value)

    def choose(self, observed, *, workers, call_limit, rho=0.0):
        if not 0 <= rho <= 1:
            raise ValueError('budget preference must be 0–1')
        limit = max(1, math.ceil(call_limit * self.stop_fraction * (1 - .75 * rho)))
        if len(observed) >= limit:
            return ()
        parents = {n.parent for n in observed}
        leaves = [n for n in observed if n.node_id not in parents]
        if self.ranking == 'best':
            leaves.sort(key=lambda n: (-(n.score if n.score is not None else -1), n.order))
        elif self.ranking == 'deepest':
            depths = {'root': 0}
            for node in observed:
                depths[node.node_id] = depths[node.parent] + 1
            leaves.sort(key=lambda n: (-depths[n.node_id], n.order))
        else:
            leaves.sort(key=lambda n: n.order)
        choices = [n.node_id for n in leaves]
        if not observed or len(observed) % self.root_every == 0:
            choices.insert(0, 'root')
        else:
            choices.append('root')
        return tuple(choices[:min(self.width, workers, limit - len(observed))])


def validate_action(observed, selected, workers):
    parents = {node.parent for node in observed}
    eligible = {'root'} | {node.node_id for node in observed if node.node_id not in parents}
    if (not isinstance(selected, (tuple, list)) or len(selected) > workers
            or any(not isinstance(item, str) for item in selected)
            or len(set(selected)) != len(selected) or not set(selected) <= eligible):
        raise ValueError('policy action must select distinct observed leaves or root within worker capacity')
