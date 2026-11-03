"""Code-owned continuous coverage, policy/model identity and retry evidence."""
from dataclasses import dataclass
import math
import re

from ...identity import digest


@dataclass(frozen=True)
class MemoryCheckpoint:
    memory: str = ''
    covered: int = 0
    offset: int = 0
    target_count: int = 0
    attempt: dict | None = None


def load_checkpoint(state, items, sources, policy, history, memory_tokens, estimate):
    if state is None:
        return MemoryCheckpoint()
    required = {'policy', 'artifact', 'covered', 'offset', 'source_prefix'}
    if not isinstance(state, dict) or set(state) not in (required, required | {'target_count', 'attempt'}):
        raise ValueError('invalid working-memory checkpoint shape')
    covered, offset = state['covered'], state['offset']
    if (type(covered) is not int or not 0 <= covered <= len(items)
            or type(offset) is not int or offset < 0 or covered == len(items) and offset):
        raise ValueError('invalid working-memory coverage cursor')
    prefix = [(item.id, sources[i]) for i, item in enumerate(items[:covered + bool(offset)])]
    if state['source_prefix'] != digest(prefix) or offset and offset >= len(sources[covered]):
        raise ValueError('working-memory source coverage no longer matches canonical history')
    target = state.get('target_count', covered + bool(offset))
    if type(target) is not int or not covered + bool(offset) <= target <= len(items):
        raise ValueError('invalid working-memory target boundary')
    attempt = state.get('attempt')
    if attempt is not None and (not isinstance(attempt, dict) or set(attempt) != {'fingerprint', 'timestamp'}
            or not isinstance(attempt['fingerprint'], str) or not re.fullmatch('[0-9a-f]{64}', attempt['fingerprint'])
            or type(attempt['timestamp']) not in (int, float) or not math.isfinite(attempt['timestamp'])
            or attempt['timestamp'] < 0):
        raise ValueError('invalid working-memory retry checkpoint')
    if state['policy'] != policy:
        return MemoryCheckpoint()
    memory = history.text(state['artifact'])
    if estimate(memory) > memory_tokens:
        raise ValueError('persisted working memory exceeds its policy bound')
    return MemoryCheckpoint(memory, covered, offset, target, attempt)


def save_checkpoint(checkpoint, items, sources, policy, history):
    return {'policy': policy, 'artifact': history.put(checkpoint.memory),
        'covered': checkpoint.covered, 'offset': checkpoint.offset,
        'source_prefix': digest([(item.id, sources[i]) for i, item in
            enumerate(items[:checkpoint.covered + bool(checkpoint.offset)])]),
        'target_count': checkpoint.target_count, 'attempt': checkpoint.attempt}
