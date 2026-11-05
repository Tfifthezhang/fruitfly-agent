"""Separate evidence coverage from execution diagnostic completeness."""
import json


def build_coverage(record, sources, artifacts, facts):
    gaps = [{'source_path': s['path'], 'reason': s.get('reason', s['status'])}
            for s in sources if s.get('status') in {'partial', 'unindexed', 'unavailable'}]
    indexed = [s for s in sources if s.get('format')]
    parsing = ('partial' if any(s.get('gaps') for s in indexed) else
               'complete' if indexed else 'unknown')
    indexing = ('partial' if gaps else 'complete' if indexed else 'unknown')
    capture = next((r for r in record.artifacts if r.path.endswith('capture-manifest.json')), None)
    collection, outputs = 'unknown', 'unknown'
    if capture:
        try:
            manifest = json.loads(artifacts.read(capture.artifact_id))
            if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), list):
                raise ValueError('invalid capture manifest')
            collection = 'complete' if manifest.get('status') == 'complete' else 'partial'
            available = {r.artifact_id for r in record.artifacts}
            for entry in manifest.get('files', []):
                if entry.get('status') == 'collected' and 'sha256:' + entry.get('sha256', '') not in available:
                    collection = 'partial'
                    gaps.append({'source_path': entry.get('path'), 'reason': 'captured bytes unavailable or invalid'})
            outputs = collection
        except (ValueError, KeyError, OSError, TypeError, AttributeError):
            collection = 'partial'
            gaps.append({'source_path': capture.path, 'reason': 'invalid capture manifest'})
    else:
        gaps.append({'source_path': 'deliverables', 'reason': 'capture scope/receipt unavailable'})
    answer = next((r for r in record.artifacts if r.path == 'diagnostics/final-answer.json'), None)
    answer_state = 'unknown'
    if answer:
        try:
            answer_state = json.loads(artifacts.read(answer.artifact_id))['state']
        except (ValueError, KeyError, OSError):
            pass
    if answer_state != 'final':
        gaps.append({'source_path': 'final-answer', 'reason': answer_state})
        if outputs == 'complete':
            outputs = 'partial'
    usage = 'unknown'
    if facts:
        totals = [v.used for v in facts.usage if v.scope == 'execution' and v.resource in {'input_tokens', 'output_tokens'}]
        if totals:
            usage = 'complete' if all(v is not None for v in totals) else 'partial'
    dimensions = {'collection': collection, 'parsing': parsing, 'indexing': indexing,
                  'outputs': outputs, 'usage': usage,
                  'identity': 'partial' if any(s['status'] == 'unavailable' for s in sources) else 'complete'}
    return {'run_id': record.run_id, 'scope': 'registered resources and declared capture roots',
            'dimensions': dimensions, 'gaps': gaps, 'final_answer_state': answer_state,
            'evidence_complete': all(v in {'complete', 'not_applicable'} for v in dimensions.values()),
            'execution_diagnostics_complete': facts.complete if facts else False}
