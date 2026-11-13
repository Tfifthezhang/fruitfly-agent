"""Apply an explicit selection grant without changing retained batch records."""
import json


def selected_records(request, artifacts):
    resources = [r for r in request.context if r.path == 'selection.json']
    if not resources:
        return request.records
    if len(resources) != 1:
        raise ValueError('investigation requires one evidence selection')
    selection = json.loads(artifacts.read(resources[0].artifact_id))
    runs = [item['run_id'] for item in selection['selected']]
    granted = {r.run_id for r in request.records}
    if len(runs) != len(set(runs)) or set(runs) - granted:
        raise ValueError('evidence selection exceeds retained record grant')
    return tuple(r for r in request.records if r.run_id in runs)


def receipt_metadata(receipt):
    """Navigation points to output/catalog bodies instead of duplicating them."""
    return {name: getattr(receipt, name) for name in ('run_id', 'task_id', 'material_id',
        'harness_id', 'conditions_id', 'initial_state_id', 'status', 'model_calls')}


def selected_materials(request, artifacts, receipt):
    resources = [r for r in request.context if r.path == 'selection.json']
    if not resources:
        return receipt.artifacts
    selection = json.loads(artifacts.read(resources[0].artifact_id))
    case = next((c for c in selection['selected'] if c['run_id'] == receipt.run_id), None)
    if case is None:
        return ()
    if 'material_paths' not in case:
        return receipt.artifacts
    paths = case['material_paths']
    if len(paths) != len(set(paths)) or set(paths) - {r.path for r in receipt.artifacts}:
        raise ValueError('selected materials exceed execution grant')
    return tuple(r for r in receipt.artifacts if r.path in paths)
