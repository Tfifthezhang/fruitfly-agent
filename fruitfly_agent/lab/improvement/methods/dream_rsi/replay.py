"""Prefix-only deterministic replay and the Dream-RSI quality/cost objective."""
from dataclasses import dataclass
import math
from ..tree_search.policy import validate_action
from ..tree_search.history import DiscoveryNode


@dataclass(frozen=True)
class ReplayResult:
    calls: int
    rounds: int
    best: float
    revealed: tuple[str, ...]


def replay(world, policy, *, workers, rounds, rho, check=lambda: None):
    if type(workers) is not int or not 1 <= workers <= 16 or type(rounds) is not int or not 1 <= rounds <= 512:
        raise ValueError('invalid replay bounds')
    observed: list[DiscoveryNode] = []
    used: set[str] = set()
    completed = 0
    for _ in range(rounds):
        check()
        selected = policy.choose(tuple(observed), workers=workers, call_limit=len(world.nodes), rho=rho)
        validate_action(observed, selected, workers)
        if not selected:
            break
        completed += 1
        for parent in selected:
            child = next((node for node in world.nodes if node.parent == parent and node.node_id not in used), None)
            if child is not None:
                used.add(child.node_id)
                observed.append(child)
        if len(observed) == len(world.nodes):
            break
    return ReplayResult(len(observed), completed,
        max((n.score for n in observed if n.score is not None), default=0.0), tuple(n.node_id for n in observed))


def score_world(world, policy, *, workers=4, rounds=64, penalty=.1, check=lambda: None):
    if not math.isfinite(penalty) or penalty < 0:
        raise ValueError('parallel penalty must be finite and nonnegative')
    best = max((n.score for n in world.nodes if n.score is not None), default=0.0)
    if best <= 0:
        raise ValueError('replay objective requires a positive recorded best score')
    results = tuple(replay(world, policy, workers=workers, rounds=rounds, rho=rho, check=check)
                    for rho in (0., .25, .5, .75, 1.))
    points = sorted({(r.calls, min(1., max(0., r.best / best))) for r in results})
    frontier = [(n, a) for n, a in points if not any(
        n2 <= n and a2 >= a and (n2 < n or a2 > a) for n2, a2 in points)]
    previous, volume = 0., 0.
    for calls, quality in frontier:
        volume += (quality - previous) * (len(world.nodes) - calls) / len(world.nodes)
        previous = quality
    parallel = sum(r.rounds / r.calls for r in results if r.calls) / len(results)
    return volume - penalty * parallel, results


def evaluate_policy(worlds, policy, **settings):
    if not worlds:
        raise ValueError('no replay worlds')
    evidence = [score_world(world, policy, **settings) for world in worlds]
    return sum(score for score, _ in evidence) / len(evidence), evidence
