"""Named text targets expose validation and host binding instructions."""
import json
import re
from fruitfly_agent.improvement.contracts.versions import canonical_json

TEXT_TARGET_PREFIX = 'text-target:'


def state_artifact_path(key):
    """Stable virtual snapshot location for a registered retained-text binding."""
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', key):
        raise ValueError('state artifact key must be a stable identifier')
    return f'.fruitfly/retained/{key}/document.md'






def validate_text(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 30_000:
        raise ValueError('candidate text must contain 1–30,000 characters')
    if any(ord(char) < 32 and char not in '\n\t' for char in text):
        raise ValueError('candidate text contains control characters')


def expand_target(snapshot, text):
    """Resolve a complete component document without knowing any concrete object."""
    if snapshot.binding.kind != 'components':
        validate_text(text)
        return ((snapshot, text),)
    if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > 2_000_000:
        raise ValueError('component document exceeds its 2MB allocation')
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError('component candidate must be a JSON object') from exc
    if (not isinstance(data, dict) or set(data) != {p.target_id for p in snapshot.components}
            or canonical_json(data) != text):
        raise ValueError('component candidate must contain exactly the registered IDs as canonical JSON')
    result = tuple((part, data[part.target_id]) for part in snapshot.components)
    for part, value in result:
        if not isinstance(value, str):
            raise ValueError('component values must be instruction text')
    return result


def target_edits(snapshot, text):
    """Return only changed leaves; unchanged components retain their bindings."""
    return tuple((part, value) for part, value in expand_target(snapshot, text) if part.text != value)
