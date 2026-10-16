"""Optimize a declarative exploration policy, then compare real discovery runs."""
from dataclasses import replace
import json
import asyncio
from types import SimpleNamespace
from .. import MethodUsage
from pathlib import Path
from fruitfly_agent.lab.algorithms import AlgorithmSpec
from ...contracts.search import SearchCandidate, SearchResult, content_id
from ...contracts.versions import canonical_json, content_hash
from ...tasks import safe_path
from ..tree_search.policy import ExplorationPolicy
from ..tree_search.history import load_worlds, save_world
from ..tree_search.improver import discover, conditions
from .replay import evaluate_policy


class DreamRsiImprover:
    spec = AlgorithmSpec('dream-rsi', 'dream-rsi-declarative-v1', 'session')
    supported_roles = frozenset({'I'})
    supported_schemas = frozenset({'exploration-policy-v1'})
    usage = MethodUsage(
        'Manual /improvement; enabling configuration starts no work.',
        'Completed matching discovery histories; training/selection and independent holdout tasks.',
        'Recorded task scores and real-search task acceptance; no human score required.',
        'Configured improver model proposes bounded policy JSON.',
        'Replay gain, then same-start paired search and independent holdout outcome/cost comparison.',
        'Review and activate the I policy artifact in a new session; H and S stay fixed.')
    confirmation_cases = ()
    objective_metric = 'replay_quality_cost_reward'
    required_capabilities = frozenset({'evaluate', 'complete', 'history', 'target-trials'})

    def __init__(self, workspace, execution_target, parameters):
        self.workspace, self.execution_target = workspace, execution_target
        self.parameters = dict(parameters)
        self.all_worlds, self.sources = load_worlds(workspace, parameters['history_path'])
        self.worlds = tuple(w for w in self.all_worlds if max((n.score for n in w.nodes if n.score is not None), default=0) > 0)
        self.excluded = tuple(w.identity for w in self.all_worlds if w not in self.worlds)

    def check_materials(self, suite, config):
        problem = SimpleNamespace(cases_digest=suite.digest, task_execution_id=suite.execution_id,
            baseline=self.execution_target.snapshot(), policy=SimpleNamespace(policy_id=suite.policy_id),
            direction=self.parameters['discovery_direction'], train=suite.train, validation=suite.validation)
        if any(world.conditions != conditions(problem, config.model) for world in self.all_worlds):
            raise ValueError('replay histories differ from current tasks, model, direction or initial target')
        if not self.worlds:
            raise ValueError('replay histories need positive scored outcomes')
        return (('Replay worlds', str(len(self.worlds))), ('Excluded zero-quality histories', str(len(self.excluded))))

    def source_identity(self):
        return [(path, content_hash(safe_path(self.workspace, Path(path)).read_text(encoding='utf-8'))) for path, _ in self.sources]

    async def evaluate(self, policy, services, parameters, settings):
        try:
            return await asyncio.wait_for(asyncio.to_thread(evaluate_policy, self.worlds, policy,
                check=services.check_cancellation, **settings), parameters['replay_timeout_seconds'])
        except TimeoutError:
            services.stop.set()
            raise

    async def search(self, problem, services):
        p = dict(problem.parameters)
        if self.source_identity() != list(self.sources):
            raise ValueError('replay histories changed after binding; preview again')
        inner = replace(problem, baseline=self.execution_target.snapshot(), direction=p['discovery_direction'])
        trials = services.for_target(inner, self.execution_target)
        expected = conditions(inner, services.config.model)
        if any(world.conditions != expected for world in self.worlds):
            raise ValueError('replay histories differ from current tasks, model or initial target')
        settings = dict(workers=p['workers'], rounds=p['replay_rounds'], penalty=p['parallel_penalty'])
        if not self.confirmation_cases:
            raise ValueError('independent confirmation tasks are required')
        confirmation = services.for_target(replace(inner, validation=self.confirmation_cases), self.execution_target)
        current = ExplorationPolicy.parse(problem.baseline.text)
        seed, initial_runs = await self.evaluate(current, services, p, settings)
        best, best_score = current, seed
        feedback = [{'score': score, 'runs': [r.__dict__ for r in runs]} for score, runs in initial_runs]
        services.record('replay-pool', sources=self.sources, worlds=[w.identity for w in self.worlds], excluded_zero_quality=self.excluded)
        for _ in range(p['policy_revisions']):
            services.check()
            response = await services.complete('improver',
                'Improve a prefix-only search policy. Return only JSON with width (1–16), root_every (1–100), '
                'ranking (best/oldest/deepest), stop_fraction (.05–1). No code. Maximize replay quality/cost reward.',
                canonical_json({'direction': problem.direction, 'current': json.loads(best.serialize()),
                    'score': best_score, 'feedback': feedback[-8:],
                    'policy_semantics': 'root_every controls branch opening; width limits parallel choices; ranking orders observed leaves; stop_fraction bounds calls.'}))
            try:
                candidate = ExplorationPolicy.parse(response)
                score, runs = await self.evaluate(candidate, services, p, settings)
            except (ValueError, TypeError) as exc:
                feedback.append({'invalid': str(exc)[:500]})
                services.record('policy-rejected', reason=str(exc)[:500])
                continue
            feedback.append({'policy': json.loads(candidate.serialize()), 'score': score})
            services.record('policy-replay', candidate_id=content_id(candidate.serialize()), score=score,
                worlds=[{'score': s, 'runs': [r.__dict__ for r in rs]} for s, rs in runs])
            if score > best_score:
                best, best_score = candidate, score
        if best.serialize() == current.serialize() or best_score - seed < p['min_replay_gain']:
            return SearchResult((), seed, 'no_replay_improvement')
        services.set_phase('Confirming exploration policy with real search')
        before, after = [], []
        for _ in range(p['confirmation_repeats']):
            for policy, results in ((current, before), (best, after)):
                world = await discover(inner, trials, policy, rounds=p['rounds'], workers=p['workers'], call_limit=p['discovery_calls'])
                if world is None or any(n.score is None for n in world.nodes):
                    return SearchResult((), seed, 'confirmation_unavailable')
                archive = safe_path(self.workspace, Path(p['history_path']))
                output = archive if archive.is_dir() else archive.parent
                path = save_world(self.workspace, output, world)
                services.record('discovery-history', path=path, world=world.identity, stage='policy-confirmation')
                chosen = max(world.nodes, key=lambda n: n.score)
                result = await confirmation.evaluate(chosen.text, 'validation')
                if result.score is None:
                    return SearchResult((), seed, 'confirmation_unavailable')
                results.append((result.score, len(world.nodes)))
        before_score = sum(s for s, _ in before) / len(before)
        after_score = sum(s for s, _ in after) / len(after)
        before_calls = sum(n for _, n in before)
        after_calls = sum(n for _, n in after)
        passed = (after_score - before_score >= p['min_online_gain'] or
                  (after_score >= before_score and after_calls < before_calls))
        services.record('policy-confirmation', passed=passed, baseline=before, candidate=after)
        if not passed:
            return SearchResult((), seed, 'confirmation_failed')
        evidence = (('Replay score', f'{seed} → {best_score}'),
            ('Independent confirmation', 'same-start real discovery comparison passed; human adoption required'),
            ('Confirmation baseline score', str(before_score)), ('Confirmation candidate score', str(after_score)),
            ('Confirmation discovery calls', f'{before_calls} → {after_calls}'),
            ('Confirmation repeats', str(p['confirmation_repeats'])),
            ('Policy representation', 'bounded declarative policy; no generated Python execution'))
        return SearchResult((SearchCandidate(best.serialize(), best_score, evidence),), seed, 'confirmed_improvement')
