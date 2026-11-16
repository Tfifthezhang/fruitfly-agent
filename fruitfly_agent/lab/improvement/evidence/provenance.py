"""Exact returned source spans, independent of temporary workspace locations."""
from fruitfly_agent.improvement.contracts.evidence import EvidenceSpan


def retain_span(workspace, path, artifact_id, start, end):
    spans = getattr(workspace, 'source_spans', None)
    if spans is None:
        spans = workspace.source_spans = {}
    citation = EvidenceSpan(artifact_id, start, end).citation_id
    spans[(path, citation)] = {'path': path, 'artifact_id': artifact_id,
        'citation_id': citation, 'start': start, 'end': end}


def source_index(workspace):
    return {'sources': [value for _, value in sorted(getattr(workspace, 'source_spans', {}).items())],
        'scope': 'Exact returned text intervals. Source identity does not certify semantic entailment.'}
