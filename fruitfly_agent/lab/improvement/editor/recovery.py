"""Explicit restoration of a granted unsubmitted draft under current owners."""
import json
import hashlib
from fruitfly_agent.improvement.contracts.components import HarnessSnapshot
from fruitfly_agent.improvement.contracts.failures import IntegrityError


def restore_draft(reference, workspace, request, artifacts, components):
    if reference not in {resource.artifact_id for resource in request.context}:
        raise ValueError('draft must be explicitly granted through stage context')
    value = json.loads(artifacts.read(reference))
    if value.get('baseline_id') != request.baseline.snapshot_id:
        raise IntegrityError('draft baseline differs from current baseline')
    snapshot = HarnessSnapshot.from_dict(value['harness'])
    components.validate(snapshot)
    changed = {component.component_id for component in snapshot.components
        if component != request.baseline.component(component.component_id)}
    if changed - set(request.plan.component_ids):
        raise IntegrityError('draft changes components outside current grants')
    sources = [source for source in value.get('sources', [])
        if not source['path'].startswith(('harness/', 'context/components/'))
        and source['path'] not in {'INDEX.json', 'context/preflight.json', 'context/components.json',
            'context/edit-grants.json', 'context/repair.json', 'context/submission.txt'}]
    for source in sources:
        data = workspace.read(source['path'])
        if 'sha256:' + hashlib.sha256(data).hexdigest() != source['artifact_id']:
            raise IntegrityError('draft evidence identity differs from current evidence')
    files = {f'harness/{component.component_id}/{file.path}': file.text.encode()
        for component in snapshot.components for file in component.files}
    retained = {path: data for path, data in workspace.files.items() if not path.startswith('harness/')}
    if sum(len(data) for data in (*retained.values(), *files.values())) > workspace.max_bytes:
        raise ValueError('restored draft exceeds workspace allocation')
    workspace.files = {**retained, **files}
    workspace.retain_draft()
    workspace.record('editor-draft-restored', artifact_id=reference,
        baseline_id=request.baseline.snapshot_id, changed_components=sorted(changed))
    return {'changed_components': sorted(changed), 'required_reads': sources,
        'note': 'Unsubmitted draft restored. Read relevant current sources and submit reasons; historical receipts do not count as current direct reading.'}
