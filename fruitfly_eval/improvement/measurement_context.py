"""Controller-authored attribution outside Agent-writable log directories."""
from pathlib import Path
import json
from fruitfly_agent.improvement.contracts.versions import require_hash

FILENAME = 'fruitfly-measurement-context.json'
RESOURCE_PATH = 'diagnostics/measurement-context.json'


def validate(value):
    if not isinstance(value, dict) or set(value) != {'origin_id', 'attempt', 'scorer_id', 'comparison'}:
        raise ValueError('invalid measurement context fields')
    if not isinstance(value['origin_id'], str) or not value['origin_id']:
        raise ValueError('measurement context needs a canonical task origin')
    if type(value['attempt']) is not int or value['attempt'] < 0:
        raise ValueError('measurement context needs a nonnegative attempt')
    require_hash(value['scorer_id'])
    comparison = value['comparison']
    if not isinstance(comparison, dict) or set(comparison) != {'material', 'conditions', 'initial_state', 'source'}:
        raise ValueError('measurement context needs complete comparison provenance')
    for key in ('material', 'conditions', 'initial_state'):
        require_hash(comparison[key])
    if not isinstance(comparison['source'], str) or not comparison['source']:
        raise ValueError('measurement context needs provenance text')
    return value


def read(directory: Path, root: Path):
    from .evidence import safe_path
    path = directory / FILENAME
    if not path.exists():
        return None
    if not path.is_file() or not safe_path(path, root.resolve()):
        raise ValueError('measurement context must stay in its controller archive')
    return validate(json.loads(path.read_text()))
