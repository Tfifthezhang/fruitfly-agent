"""Strict candidate submission, independent of evidence reading and model prose."""
import json
from fruitfly_agent.improvement.contracts.pipeline import CandidateBundle, EditReason


def submission(text, workspace, request, components):
    def unique(pairs):
        values = {}
        for key, value in pairs:
            if key in values:
                raise ValueError('duplicate submission field: ' + key)
            values[key] = value
        return values
    value = json.loads(text, object_pairs_hook=unique) if isinstance(text, str) else text
    if not isinstance(value, dict) or set(value) != {'reasons'} or not isinstance(value['reasons'], list):
        raise ValueError('editor must submit exactly a reasons array')
    reasons = tuple(EditReason(**r) for r in value['reasons'])
    candidate = CandidateBundle(request.plan.parent, request.baseline, workspace.collect(),
        request.plan.generator_id, reasons)
    components.validate(candidate.harness)
    changed = set(candidate.changed_ids)
    known = {r.run_id for r in request.records}
    if (changed - set(request.plan.component_ids) or len(reasons) != len(changed)
            or {r.component_id for r in reasons} != changed
            or any(set(r.evidence_ids) - known for r in reasons)):
        raise ValueError('each authorized changed component must cite supplied executions exactly once')
    workspace.access.validate_citations(reasons)
    return candidate
