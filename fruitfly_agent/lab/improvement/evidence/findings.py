"""Validate one bounded, attributed worker result block."""
import json
from fruitfly_agent.improvement.contracts.versions import canonical_json


def validate_findings_block(value, scope, maximum):
    if set(value) != {'summary', 'sources', 'unknowns'} or not isinstance(value['summary'], str) or not value['summary'].strip():
        raise ValueError('findings require summary, sources and unknowns')
    if len(value['summary']) > maximum or not isinstance(value['sources'], list):
        raise ValueError(f'findings size exceeds {maximum} characters; use save_findings for separate blocks')
    if not isinstance(value['unknowns'], list) or any(not isinstance(v, str) or len(v) > maximum for v in value['unknowns']):
        raise ValueError('unknowns must be bounded text entries')
    for source in value['sources']:
        if (not isinstance(source, dict) or set(source) != {'path', 'citation_id'}
                or source['path'] not in scope.paths()
                or source['citation_id'] not in scope.provided_paths.get(source['path'], set())):
            raise ValueError('findings cite unassigned or unread source spans')
    frozen = canonical_json(value)
    if len(frozen) > maximum:
        raise ValueError(f'findings size exceeds {maximum} characters; use save_findings for separate blocks')
    return json.loads(frozen)
