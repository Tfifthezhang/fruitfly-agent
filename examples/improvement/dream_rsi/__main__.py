"""Compare policies on a synthetic tree; no model or environment calls."""
from fruitfly_agent.lab.improvement.methods.tree_search.history import DiscoveryNode, DiscoveryWorld
from fruitfly_agent.lab.improvement.methods.tree_search.policy import ExplorationPolicy
from fruitfly_agent.lab.improvement.methods.dream_rsi.replay import score_world


def main():
    world = DiscoveryWorld('synthetic-example', (
        DiscoveryNode('n0', 'root', 0, 'first', .2),
        DiscoveryNode('n1', 'root', 1, 'second', .3),
        DiscoveryNode('n2', 'n0', 2, 'refined first', 1.),))
    baseline = ExplorationPolicy()
    candidate = ExplorationPolicy(root_every=100, stop_fraction=.5)
    before, _ = score_world(world, baseline)
    after, _ = score_world(world, candidate)
    print(f'Synthetic replay objective: {before:.6f} -> {after:.6f}')
    print('Replay comparison only; no real-search confirmation or activation performed.')
    return 0 if after > before else 1


if __name__ == '__main__':
    raise SystemExit(main())
