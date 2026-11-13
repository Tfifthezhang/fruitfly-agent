"""Validate investigation findings without treating hypotheses as verified causes."""
from fruitfly_agent.improvement.contracts.validation import identifier, bounded

FINDING_FIELDS = ('issue_id', 'signal', 'facts', 'hypotheses', 'counterevidence', 'unknowns', 'sources')


def validate_findings(findings):
    if not isinstance(findings, list) or len(findings) > 16:
        raise ValueError('organization findings must be a bounded array')
    seen = set()
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != set(FINDING_FIELDS):
            raise ValueError('finding requires identity, signal, facts, hypotheses, counterevidence, unknowns and sources')
        identifier(finding['issue_id'])
        if finding['issue_id'] in seen:
            raise ValueError('finding issue identities must be distinct')
        seen.add(finding['issue_id'])
        bounded(finding['signal'], 2000)
        for key in ('facts', 'hypotheses', 'counterevidence', 'unknowns'):
            values = finding[key]
            if not isinstance(values, list) or len(values) > 16 or key == 'facts' and not values:
                raise ValueError('finding facts and uncertainties must be bounded lists')
            for value in values:
                bounded(value, 4000)
        if not isinstance(finding['sources'], list) or not finding['sources']:
            raise ValueError('finding requires supplied source spans')
