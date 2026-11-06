"""Strict retained memory grammar and explicit update operations."""
import re
from copy import deepcopy
from fruitfly_agent.lab.context_manager.augmentation.memory.methods.file_memory.models import KINDS

FIELDS = {'id', 'kind', 'scope', 'subject', 'description', 'body', 'applicability',
          'provenance', 'observed_at', 'status', 'supersedes'}


def validate_memories(entries):
    if not isinstance(entries, list) or len(entries) > 128:
        raise ValueError('memory library requires at most 128 entries')
    identities = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != FIELDS:
            raise ValueError('invalid memory fields')
        if (not isinstance(entry['id'], str) or not re.fullmatch(r'memory-[a-zA-Z0-9_-]+', entry['id'])
                or entry['id'] in identities):
            raise ValueError('invalid or duplicate memory identity')
        identities.add(entry['id'])
        if not isinstance(entry['kind'], str) or entry['kind'] not in KINDS or entry['scope'] != 'project' or not isinstance(entry['status'], str) or entry['status'] not in {'active', 'withdrawn'}:
            raise ValueError('invalid memory kind, scope or status')
        for field in ('subject', 'description', 'body', 'applicability', 'observed_at'):
            value = entry[field]
            limit = 16000 if field == 'body' else 1000
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ValueError('invalid memory ' + field)
        source = entry['provenance']
        if (not isinstance(source, dict) or set(source) != {'session_id', 'message_ids', 'basis'}
                or not isinstance(source['session_id'], str) or not source['session_id']
                or not isinstance(source['basis'], str) or source['basis'] not in {'explicit', 'inferred'}
                or not isinstance(source['message_ids'], list) or not source['message_ids']
                or any(not isinstance(v, str) or not v for v in source['message_ids'])):
            raise ValueError('invalid memory provenance')
        if (not isinstance(entry['supersedes'], list) or any(not isinstance(v, str) for v in entry['supersedes'])
                or len(set(entry['supersedes'])) != len(entry['supersedes'])):
            raise ValueError('invalid memory replacement references')
    graph = {e['id']: e['supersedes'] for e in entries}
    visited = set()
    def visit(key, trail):
        if key in trail:
            raise ValueError('cyclic memory replacement')
        if key in visited:
            return
        for previous in graph[key]:
            if previous not in graph:
                raise ValueError('unknown superseded memory')
            visit(previous, trail | {key})
        visited.add(key)
    for key in graph:
        visit(key, set())
    return deepcopy(entries)


def apply_changes(entries, changes, *, evidence, observed_at):
    """Preserve omitted entries; additions must cite the exact supplied evidence."""
    current = {e['id']: e for e in validate_memories(entries)}
    if not isinstance(changes, list) or len(changes) > 128:
        raise ValueError('memory changes require a bounded list')
    known = {item.identity: item for item in evidence}
    touched = set()
    for index, change in enumerate(changes):
        if not isinstance(change, dict) or not isinstance(change.get('operation'), str) or change.get('operation') not in {'add', 'update', 'withdraw'}:
            raise ValueError('invalid memory change operation')
        operation = change['operation']
        if operation == 'withdraw':
            if set(change) != {'operation', 'id'} or not isinstance(change['id'], str) or change['id'] not in current:
                raise ValueError('invalid memory withdrawal')
            key = change['id']
            entry = {**current[key], 'status': 'withdrawn'}
        else:
            if set(change) != {'operation', 'entry', 'evidence_ids'}:
                raise ValueError('invalid memory change fields')
            citations = change['evidence_ids']
            if (not isinstance(citations, list) or not citations or any(not isinstance(v, str) or v not in known for v in citations)
                    or len(set(citations)) != len(citations)):
                raise ValueError('memory update cites unavailable evidence')
            value = change['entry']
            allowed = {'kind', 'subject', 'description', 'body', 'applicability', 'supersedes'}
            if not isinstance(value, dict) or set(value) != (allowed | ({'id'} if operation == 'update' else set())):
                raise ValueError('invalid memory proposal fields')
            import hashlib
            proposed_key = value.get('id') if operation == 'update' else 'memory-' + hashlib.sha256(
                ('|'.join(citations) + ':' + str(index) + ':' + repr(sorted(value.items()))).encode()).hexdigest()[:24]
            if not isinstance(proposed_key, str):
                raise ValueError('invalid memory update identity')
            key = proposed_key
            if operation == 'add' and key in current:
                raise ValueError('memory addition identity conflict')
            if operation == 'update' and key not in current:
                raise ValueError('unknown memory update identity')
            source = known[citations[0]]
            if any(known[c].session_id != source.session_id for c in citations):
                raise ValueError('one memory update must cite one session')
            entry = {**value, 'id': key, 'scope': 'project', 'status': 'active',
                'provenance': {'session_id': source.session_id,
                    'message_ids': [known[c].message_id for c in citations], 'basis': 'inferred'},
                'observed_at': observed_at}
        if key in touched:
            raise ValueError('duplicate change for memory')
        touched.add(key)
        current[key] = entry
    return validate_memories([current[k] for k in sorted(current)])
