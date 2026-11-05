"""Attributed retained-content fixtures shared across behavior owners."""
def memory(identity='memory-editor', *, description='Read for editor preferences.', body='Prefer editor A.'):
    return {'id': identity, 'kind': 'preference', 'scope': 'project', 'subject': 'editor',
        'description': description, 'body': body, 'applicability': 'Editing project files.',
        'provenance': {'session_id': 'session-a', 'message_ids': ['session:1'], 'basis': 'explicit'},
        'observed_at': '2026-01-01T00:00:00Z', 'status': 'active', 'supersedes': []}
