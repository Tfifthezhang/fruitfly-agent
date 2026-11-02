"""Code-owned source identity, active artifact dependencies and retry admission."""
import hashlib
import json
import re


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def source_hash(items):
    return digest([(item.id, item.message.to_dict()) for item in items])


def validate_state(value, items, history):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {'policy', 'source_count', 'source_hash', 'artifacts', 'attempt'}:
        raise ValueError('invalid layered-compaction checkpoint shape')
    count = value['source_count']
    if (type(count) is not int or not 0 <= count <= len(items)
            or value['source_hash'] != source_hash(items[:count])
            or not isinstance(value['policy'], str) or not re.fullmatch('[0-9a-f]{64}', value['policy'])):
        raise ValueError('layered-compaction source identity mismatch')
    artifacts = value['artifacts']
    if (not isinstance(artifacts, list) or len(artifacts) > 128
            or any(not isinstance(item, str) for item in artifacts)
            or len(set(artifacts)) != len(artifacts)):
        raise ValueError('invalid layered-compaction artifact dependencies')
    for reference in artifacts:
        history.text(reference)
    attempt = value['attempt']
    if attempt is not None and (not isinstance(attempt, dict)
            or set(attempt) != {'fingerprint', 'source_count', 'outcome'}
            or not isinstance(attempt['fingerprint'], str) or not re.fullmatch('[0-9a-f]{64}', attempt['fingerprint'])
            or type(attempt['source_count']) is not int or not 0 <= attempt['source_count'] <= count
            or attempt['outcome'] not in {'succeeded', 'failed'}):
        raise ValueError('invalid layered-compaction summary attempt')
    return value


def may_summarize(previous, policy, fingerprint, source_count):
    if previous is None or previous['policy'] != policy or previous['attempt'] is None:
        return True
    attempt = previous['attempt']
    if attempt['fingerprint'] == fingerprint:
        return False
    # Fixed integrity policy: no repeated requests for unchanged/near-identical evidence.
    return source_count - attempt['source_count'] >= 8
