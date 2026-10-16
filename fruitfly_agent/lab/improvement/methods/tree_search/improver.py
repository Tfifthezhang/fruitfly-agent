"""Real parent-linked text discovery with a replaceable exploration policy."""
import asyncio
import json
from .. import MethodUsage
from fruitfly_agent.lab.algorithms import AlgorithmSpec
from ...contracts.search import SearchCandidate, SearchResult, content_id
from ...contracts.versions import canonical_json
from ...runtime.services import BudgetExhausted
from .policy import ExplorationPolicy, validate_action
from .history import DiscoveryNode, DiscoveryWorld, save_world


def conditions(problem, model):
    return content_id(canonical_json({'cases': problem.cases_digest, 'execution': problem.task_execution_id,
        'target': problem.baseline.content_hash, 'model': model, 'policy': problem.policy.policy_id,
        'generator': 'text-discovery-v1', 'direction': problem.direction,
        'train': [c.case_id for c in problem.train], 'selection': [c.case_id for c in problem.validation]}))


async def discover(problem, services, policy, *, rounds, workers, call_limit, rho=0.0):
    nodes: list[DiscoveryNode] = []
    try:
        for _ in range(rounds):
            services.check()
            selected = policy.choose(tuple(nodes), workers=workers, call_limit=call_limit, rho=rho)
            validate_action(nodes, selected, workers)
            if not selected:
                break
            async def attempt(parent):
                ancestors, cursor = [], parent
                by_id = {n.node_id: n for n in nodes}
                while cursor != 'root':
                    node = by_id[cursor]
                    ancestors.append({'text': node.text, 'score': node.score, 'feedback': node.feedback})
                    cursor = node.parent
                prompt = canonical_json({'direction': problem.direction, 'baseline': problem.baseline.text,
                    'parent_history': list(reversed(ancestors)),
                    'training': [{'input': c.input, 'expected': c.expected} for c in problem.train]})
                try:
                    text = await services.complete('improver',
                        'Propose one improved instruction text from the parent history. Return a JSON object with only "text".', prompt)
                    value = json.loads(text)
                    if not isinstance(value, dict) or set(value) != {'text'}:
                        raise ValueError('expected one candidate text')
                    text = value['text']
                    services.validate(text)
                    train = await services.evaluate(text, 'train')
                    result = await services.evaluate(text, 'validation')
                    score = result.score if train.score is not None else None
                    feedback = canonical_json([{'output': o.output, 'feedback': o.feedback} for o in train.observations])[:4000]
                    return text, score, 'scored' if score is not None else 'error', feedback
                except (BudgetExhausted, asyncio.CancelledError):
                    raise
                except (ValueError, TypeError, KeyError) as exc:
                    return '', None, 'error', str(exc)[:4000]
            tasks = [asyncio.create_task(attempt(parent)) for parent in selected]
            try:
                results = await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            for parent, (text, score, status, feedback) in zip(selected, results):
                node = DiscoveryNode(f'n{len(nodes)}', parent, len(nodes), text, score, status, feedback)
                nodes.append(node)
                services.record('discovery-node', node=node.__dict__)
    except BudgetExhausted:
        services.record("discovery-stop", reason="budget_exhausted")
    return DiscoveryWorld(conditions(problem, services.config.model), tuple(nodes)) if nodes else None


class TreeSearchImprover:
    usage = MethodUsage('Manual /improvement.', 'Training and selection tasks with declared acceptance.',
        'Task executions scored by the configured task policy.', 'Fixed text-discovery model guided by the selected parent history.',
        'Rank by selection score; this search alone does not provide independent confirmation.',
        'Review H text candidates; generated histories can support later I policy improvement.')
    spec = AlgorithmSpec('tree-search', 'text-tree-search-v1', 'session')
    supported_roles = frozenset({'H'})
    supported_schemas = frozenset({'text-v1'})
    required_capabilities = frozenset({'evaluate', 'complete', 'history'})

    def __init__(self, policy=None, workspace=None):
        self.policy = policy or ExplorationPolicy()
        self.workspace = workspace

    async def search(self, problem, services):
        p = dict(problem.parameters)
        baseline = await services.evaluate(problem.baseline.text, 'validation')
        world = await discover(problem, services, self.policy, rounds=p['rounds'], workers=p['workers'], call_limit=p['discovery_calls'])
        if world is None:
            return SearchResult((), baseline.score, 'no_discovery')
        evidence = [('Discovery world', world.identity)]
        if self.workspace is not None:
            path = save_world(self.workspace, p['history_path'], world)
            evidence.append(('Discovery history', path))
        scored = [n for n in world.nodes if n.score is not None and n.text != problem.baseline.text]
        scored.sort(key=lambda n: -n.score)
        unique: dict[str, SearchCandidate] = {}
        for node in scored:
            if node.score is not None:
                unique.setdefault(node.text, SearchCandidate(node.text, node.score, tuple(evidence)))
        return SearchResult(tuple(unique.values())[:3], baseline.score)
