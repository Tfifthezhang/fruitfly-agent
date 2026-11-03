"""Shared stable policy/evidence hashing; no algorithm-specific state schema."""
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
