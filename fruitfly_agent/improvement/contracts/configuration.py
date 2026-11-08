"""Report configuration differences without turning them into admission decisions."""
from .versions import canonical_json


def configuration_differences(before, after, prefix=''):
    if isinstance(before, dict) and isinstance(after, dict):
        rows = []
        for key in sorted(before.keys() | after.keys()):
            path = prefix + '.' + key if prefix else key
            if key not in before:
                rows.append({'path': path, 'change': 'added', 'after': after[key]})
            elif key not in after:
                rows.append({'path': path, 'change': 'removed', 'before': before[key]})
            else:
                rows.extend(configuration_differences(before[key], after[key], path))
        return rows
    if canonical_json(before) == canonical_json(after):
        return []
    return [{'path': prefix, 'change': 'changed', 'before': before, 'after': after}]
