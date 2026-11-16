"""Proposal intent is separate from a candidate's immutable component identity."""
from fruitfly_agent.improvement.contracts.editing import ProposalDecision


def validate_decision(value, candidate, findings):
    if value is None:
        if not candidate.changed_ids:
            raise ValueError('decision: explain retain_baseline or needs_evidence explicitly')
        # Existing third-party text submissions retain their exact edit reasons.
        return ProposalDecision('candidate', '; '.join(r.explanation for r in candidate.reasons),
            'Not reported by the submission; historical applicability is unknown.')
    decision = ProposalDecision(**value)
    if (decision.kind == 'candidate') != bool(candidate.changed_ids):
        raise ValueError('decision.kind does not match actual component changes')
    for issue in decision.issues:
        if issue['issue_id'] not in findings:
            raise ValueError('decision cites an unknown or ambiguous issue identity')
    selected = {issue['issue_id'] for issue in decision.issues if issue['disposition'] == 'selected'}
    referenced = {issue for reason in candidate.reasons for issue in reason.issue_ids}
    if referenced - selected:
        raise ValueError('decision must select every issue supporting a component change')
    if decision.kind != 'candidate' and selected:
        raise ValueError('a decision without changes cannot select an issue for editing')
    return decision
