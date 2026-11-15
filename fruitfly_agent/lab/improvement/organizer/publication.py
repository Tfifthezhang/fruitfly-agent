"""Publish compact issue navigation and machine-derived reading coverage."""
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from .findings import finding_sources


def publish_investigation(guide, workspace, records):
    namespace = content_hash(canonical_json(guide))
    details = {'findings/' + finding['issue_id'] + '.json': {
        **finding, 'organization_id': namespace, 'sources': finding_sources(finding)}
        for finding in guide['findings']}
    selected = sorted({path.split('/')[2] for path in workspace.paths()
        if path.startswith('context/executions/')})
    coverage = {'population_count': len(records), 'selected_count': len(selected),
        'selected_execution_ids': selected, 'direct_reading': workspace.access.inspection(),
        'delegated_citations': {path: sorted(ids) for path, ids in workspace.delegated_paths.items()},
        'children': getattr(workspace, 'investigation_children', []),
        'scope': 'Selection, returned text and child results are separate; no complete reading claim.'}
    return {**details, 'index.json': {'schema_version': 2, 'organization_id': namespace,
        'issues': [{'issue_id': f['issue_id'], 'issue_ref': namespace + '/' + f['issue_id'], 'signal': f['signal'], 'status': f['status'],
            'path': 'findings/' + f['issue_id'] + '.json'} for f in guide['findings']],
        'coverage': 'coverage.json', 'gaps': 'gaps.json', 'guide': 'guide.json'},
        'coverage.json': coverage,
        'gaps.json': {'issues': [{'issue_id': f['issue_id'], 'unknowns': f['unknowns']}
            for f in guide['findings'] if f['unknowns']], 'children': coverage['children']}}
