"""Strict candidate submission, independent of evidence reading and model prose."""
import json
from fruitfly_agent.core.tool_runtime.schema import validate_tool_arguments
from .schema import SUBMISSION
from .decision import validate_decision
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason


def submission(text, workspace, request, components):
    def unique(pairs):
        values = {}
        for key, value in pairs:
            if key in values:
                raise ValueError('duplicate submission field: ' + key)
            values[key] = value
        return values
    value = json.loads(text, object_pairs_hook=unique) if isinstance(text, str) else text
    checked = validate_tool_arguments(SUBMISSION, value)
    if not checked.is_ok:
        raise ValueError(checked.error)
    value = checked.unwrap()
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
    findings: dict[str, dict] = {}
    aliases = {}
    for resource in request.context:
        if resource.path.rsplit('/', 1)[-1] != 'guide.json':
            continue
        path = 'context/extensions/' + resource.path
        guide = json.loads(workspace.read(path))
        for finding in guide.get('findings', ()):
            issue = finding['issue_id']
            qualified = resource.artifact_id + '/' + issue
            findings[qualified] = finding
            aliases.setdefault(issue, []).append(qualified)
    for issue, identities in aliases.items():
        if len(set(identities)) == 1:
            findings[issue] = findings[identities[0]]
    for reason in reasons:
        if (set(reason.issue_ids) - findings.keys()
                or findings and not reason.issue_ids):
            raise ValueError('candidate changes must link to supplied investigation findings')
    workspace.proposal_decision = validate_decision(value.get('decision'), candidate, findings)
    return candidate
