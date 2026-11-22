"""Strict investigation submissions; historical guides are consumed separately."""
from fruitfly_agent.improvement.contracts.validation import identifier, bounded
from fruitfly_agent.improvement.contracts.organization import InvestigationFact, InvestigationGap

FINDING_FIELDS = ('issue_id', 'signal', 'facts', 'hypotheses', 'counterevidence', 'unknowns', 'run_ids', 'control_ids', 'status')


def finding_sources(finding):
    return [source for fact in finding['facts'] for source in fact['sources']]


def validate_findings(findings):
    if not isinstance(findings, list):
        raise ValueError('organization findings must be an array')
    if len(findings) > 16:
        raise ValueError(f'findings: received {len(findings)} entries; maximum 16. Merge overlapping issues and recheck the saved draft.')
    seen = set()
    for index, finding in enumerate(findings):
        prefix = f'findings[{index}]'
        if not isinstance(finding, dict) or set(finding) != set(FINDING_FIELDS):
            raise ValueError(prefix + ': requires facts, hypotheses, counterevidence, gaps, scope and status')
        identifier(finding['issue_id'])
        if finding['issue_id'] in seen:
            raise ValueError(prefix + ': duplicate issue identity')
        seen.add(finding['issue_id'])
        bounded(finding['signal'], 2000)
        if finding['status'] not in {'ready_for_proposal', 'needs_evidence', 'not_supported'}:
            raise ValueError(prefix + ': invalid investigation status')
        for key in ('facts', 'hypotheses', 'counterevidence', 'unknowns', 'run_ids', 'control_ids'):
            values = finding[key]
            if not isinstance(values, list) or len(values) > 16 or key == 'facts' and not values:
                raise ValueError(prefix + '.' + key + ': invalid bounded array')
            for value in values:
                if key == 'facts':
                    InvestigationFact(**value)
                elif key == 'unknowns':
                    InvestigationGap(**value)
                elif key in {'run_ids', 'control_ids'}:
                    identifier(value)
                else:
                    bounded(value, 4000)
        for key in ('run_ids', 'control_ids'):
            if len(finding[key]) != len(set(finding[key])):
                raise ValueError(prefix + ': duplicate execution scope')
        if set(finding['run_ids']) & set(finding['control_ids']):
            raise ValueError(prefix + ': affected and control executions must be distinct')
