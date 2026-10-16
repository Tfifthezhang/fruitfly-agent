"""Role-neutral preparation and verification; adoption remains host-owned."""
from dataclasses import dataclass

from fruitfly_agent.lab.improvement.contracts import ImprovementRequest, ImprovementAdapter, ImprovementComparison
from fruitfly_agent.lab.improvement.contracts.candidates import TargetRegistry, VersionCandidate


@dataclass(frozen=True)
class ImprovementCapability:
    adapter: ImprovementAdapter
    comparison: ImprovementComparison


class ImprovementWorkflow:
    """Embedding hosts register executable role/target/policy capabilities.

    Only explicitly registered scope/policy pairs run. A successful run returns verified
    evidence; the caller decides whether to publish or activate the candidate.
    """
    def __init__(self, targets: TargetRegistry):
        self.targets = targets
        self.capabilities: dict[tuple[str, str, str], ImprovementCapability] = {}

    def register(self, role, target_id, policy_id, capability):
        key = (role, target_id, policy_id)
        if role not in {'H', 'S', 'I'} or not target_id or not policy_id or key in self.capabilities:
            raise ValueError('invalid or duplicate improvement capability')
        self.capabilities[key] = capability

    async def run(self, request: ImprovementRequest, *, generate, active_version, adopt=None):
        capability = self.capabilities.get((request.role, request.target_id, request.policy_id))
        if capability is None:
            raise ValueError('no executable target and comparison for this role')
        if active_version() != request.parent:
            raise ValueError('improvement parent H/S/I is stale')
        candidate = await generate(request)
        if not isinstance(candidate, VersionCandidate):
            raise ValueError('generation must return a version candidate')
        self.targets.validate(candidate, request.parent)
        if len(candidate.changes) != 1 or (candidate.changes[0].role, candidate.changes[0].target_id) != (request.role, request.target_id):
            raise ValueError('one job may modify only its declared role and target')
        trial = await capability.adapter.prepare(request, candidate)
        try:
            evidence = await capability.comparison.compare(request, candidate, trial)
        finally:
            await capability.adapter.close(trial)
        from fruitfly_agent.lab.improvement.contracts import ComparisonEvidence
        if not isinstance(evidence, ComparisonEvidence) or (
            evidence.candidate_id, evidence.conditions_id, evidence.policy_id
        ) != (candidate.candidate_id, request.conditions_id, request.policy_id):
            raise ValueError('verification does not match candidate and frozen conditions')
        if active_version() != request.parent:
            raise ValueError('improvement parent changed during comparison')
        if evidence.passed and adopt is not None:
            await adopt(request, candidate, evidence)
            if active_version() != candidate.version:
                raise ValueError('host did not activate the verified version')
        return candidate, evidence


async def run_search(strategy, problem, services, *, controller=None, prepared=None):
    """Run a method through shared validation and cancellation boundaries.

    Controllers may choose their own order of trials and updates. They share the
    host's root services and cannot activate production candidates.
    """
    from fruitfly_agent.lab.improvement.contracts.search import SearchResult
    if problem.baseline.role not in getattr(strategy, 'supported_roles', {'H'}):
        raise ValueError('method does not support the requested H/S/I role')
    if problem.baseline.schema not in strategy.supported_schemas:
        raise ValueError('method does not support the requested target format')
    services.check_cancellation()
    if controller is None:
        result = await strategy.search(problem, services)
    else:
        result = await controller.search(strategy, problem, services, prepared)
    services.check_cancellation()
    if not isinstance(result, SearchResult):
        raise ValueError('method must return a search result')
    for candidate in result.candidates:
        services.validate(candidate.text)
    return result
