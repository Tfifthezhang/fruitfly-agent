"""Validate a detached candidate without executing or selecting it."""
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle


def validate_candidate(candidate, *, components, plan, baseline, records):
    if not isinstance(candidate, CandidateBundle) or candidate.parent != plan.parent or candidate.base != baseline:
        raise ValueError('candidate must match its frozen parent and editing baseline')
    if set(candidate.changed_ids) - set(plan.component_ids):
        raise ValueError('candidate changed an undeclared component')
    allowed = {record.run_id for record in records}
    changed, covered = set(candidate.changed_ids), set()
    for reason in candidate.reasons:
        if reason.component_id not in changed or set(reason.evidence_ids) - allowed:
            raise ValueError('edit attribution is outside the supplied execution evidence')
        covered.add(reason.component_id)
    if changed - covered:
        raise ValueError('each changed component needs execution evidence')
    components.validate(candidate.harness)
