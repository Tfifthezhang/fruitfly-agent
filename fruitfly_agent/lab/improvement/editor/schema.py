"""One submission schema for tool arguments and text handoffs."""
TEXT = {'type': 'string'}
STRINGS = {'type': 'array', 'items': TEXT}
REASON = {'type': 'object', 'properties': {'component_id': TEXT, 'explanation': TEXT,
    'expected_effect': TEXT, 'evidence_ids': STRINGS, 'issue_ids': STRINGS},
    'required': ['component_id', 'explanation', 'expected_effect', 'evidence_ids'], 'additionalProperties': False}
ISSUE = {'type': 'object', 'properties': {'issue_id': TEXT, 'explanation': TEXT,
    'disposition': {'type': 'string', 'enum': ['selected', 'rejected', 'deferred']}},
    'required': ['issue_id', 'disposition', 'explanation'], 'additionalProperties': False}
DECISION = {'type': 'object', 'properties': {'kind': {'type': 'string',
    'enum': ['candidate', 'retain_baseline', 'needs_evidence']}, 'explanation': TEXT,
    'baseline_applicability': TEXT, 'issues': {'type': 'array', 'items': ISSUE}, 'required_materials': STRINGS},
    'required': ['kind', 'explanation', 'baseline_applicability'], 'additionalProperties': False}
SUBMISSION = {'type': 'object', 'properties': {'reasons': {'type': 'array', 'items': REASON},
    'decision': DECISION}, 'required': ['reasons'], 'additionalProperties': False}
