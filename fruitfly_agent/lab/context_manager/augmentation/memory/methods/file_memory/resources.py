"""Freeze memory content for ordinary read tools and isolated trials."""
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.lab.context_manager.augmentation.memory.methods.file_memory.validation import validate_memories
from fruitfly_agent.lab.context_manager.augmentation.memory.methods.file_memory.index import render_catalog


def mount_memories(resources, entries):
    entries = validate_memories(entries)
    docs = {e['id'] + '.md': (canonical_json(e) + '\n').encode() for e in entries}
    prefix = resources.mount('retained-memory', lambda path: docs[path])
    locations = {e['id']: prefix + e['id'] + '.md' for e in entries}
    docs['INDEX.md'] = render_catalog(entries, locations).encode()
    return {**locations, '__catalog__': prefix + 'INDEX.md'}
