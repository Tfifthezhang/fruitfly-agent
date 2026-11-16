"""Offline workspace dependency checks before a research model starts."""


def inspect_workspace(workspace, settings):
    missing = []
    inspected = []
    for path in workspace.paths():
        # Original trajectories remain lazy. Inspect only stage entry documents
        # and candidate source files; source intervals are verified when read.
        if not (path == 'INDEX.json' or path.startswith('harness/')
                or path in {'context/batch.json', 'context/edit-grants.json', 'context/components.json'}):
            continue
        inspected.append(path)
        try:
            workspace.read(path)
        except (ValueError, KeyError, OSError) as exc:
            missing.append({'path': path, 'error': type(exc).__name__, 'reason': str(exc)[:1000]})
    report = {'path_count': len(workspace.paths()), 'inspected_paths': inspected, 'unavailable': missing,
        'writable_components': sorted(workspace.writable_ids),
        'evidence_limits': settings.to_dict(),
        'scope': 'Host dependency inspection; no model reading or success claim.'}
    workspace.record('research-preflight', **report)
    if missing:
        raise ValueError('research preflight: required entry documents unavailable: ' + ', '.join(row['path'] for row in missing))
    return report
