"""Replay is deterministic, prefix-only and grounded in recorded outcomes."""
from dataclasses import replace
import tempfile
from pathlib import Path
import unittest
from fruitfly_agent.lab.improvement.methods.tree_search.policy import ExplorationPolicy
from fruitfly_agent.lab.improvement.methods.tree_search.history import DiscoveryNode, DiscoveryWorld, load_worlds, save_world
from fruitfly_agent.lab.improvement.methods.dream_rsi.replay import replay, score_world, evaluate_policy


def world():
    return DiscoveryWorld('fixed-conditions', (
        DiscoveryNode('n0', 'root', 0, 'first', .2),
        DiscoveryNode('n1', 'root', 1, 'second', .3),
        DiscoveryNode('n2', 'n0', 2, 'better', 1.),))


class DreamReplayTests(unittest.TestCase):
    def test_replay_reveals_only_recorded_children_in_parent_order(self):
        seen = []
        class Policy:
            def choose(self, observed, **kwargs):
                seen.append(tuple(n.node_id for n in observed))
                return [('root',), ('n0',), ()][len(seen)-1]
        result = replay(world(), Policy(), workers=1, rounds=8, rho=0)
        self.assertEqual(seen, [(), ('n0',), ('n0', 'n2')])
        self.assertEqual(result.revealed, ('n0', 'n2'))
        self.assertEqual((result.calls, result.rounds, result.best), (2, 2, 1.))

    def test_objective_matches_pareto_area_and_parallel_penalty(self):
        class One:
            def choose(self, observed, **kwargs):
                return () if observed else ('root',)
        score, runs = score_world(world(), One(), penalty=.1)
        self.assertAlmostEqual(score, .2 * (3-1)/3 - .1)
        self.assertEqual(len(runs), 5)
        self.assertEqual(evaluate_policy((world(), world()), One())[0], score)
        self.assertGreater(score_world(world(), ExplorationPolicy(root_every=100, stop_fraction=.5))[0],
                           score_world(world(), ExplorationPolicy())[0])

    def test_empty_zero_and_invalid_histories_are_not_valid_scores(self):
        with self.assertRaises(ValueError):
            DiscoveryWorld('x', ())
        with self.assertRaises(ValueError):
            DiscoveryWorld('x', (DiscoveryNode('n0', 'missing', 0, '', 1),))
        with self.assertRaises(ValueError):
            DiscoveryWorld('x', (DiscoveryNode('n0', 'root', 0, '', 1),
                DiscoveryNode('n1', 'n0', 1, '', 1), DiscoveryNode('n2', 'n0', 2, '', 1)))
        with self.assertRaises(ValueError):
            score_world(DiscoveryWorld('x', (DiscoveryNode('n0', 'root', 0, '', 0),)), ExplorationPolicy())
        with self.assertRaises(ValueError):
            DiscoveryNode('n0', 'root', 0, '', 0, 'error')

    def test_policy_is_bounded_data_and_cannot_execute_code(self):
        for text in ('import os', '{}', '{"width":1,"width":2}', ExplorationPolicy().serialize().replace('"best"', '"eval"')):
            with self.assertRaises(ValueError):
                ExplorationPolicy.parse(text)
        for kwargs in ({'width': True}, {'root_every': 0}, {'stop_fraction': float('nan')}):
            with self.assertRaises(ValueError):
                ExplorationPolicy(**kwargs)
        self.assertEqual(ExplorationPolicy.parse(ExplorationPolicy().serialize()), ExplorationPolicy())

    def test_history_storage_and_workspace_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            save_world(root, 'histories', world())
            worlds, sources = load_worlds(root, 'histories')
            self.assertEqual(worlds, (world(),))
            self.assertEqual(len(sources), 1)
            with self.assertRaises(ValueError):
                load_worlds(root, 'missing')
            with self.assertRaises(ValueError):
                save_world(root, '../outside', world())


    def test_policy_cannot_reveal_unobserved_nodes_or_duplicate_workers(self):
        for action in (('n0',), ('root', 'root'), ('root', 'n0')):
            with self.subTest(action=action):
                class Invalid:
                    def choose(self, observed, **kwargs):
                        return action
                with self.assertRaises(ValueError):
                    replay(world(), Invalid(), workers=2, rounds=4, rho=0)
