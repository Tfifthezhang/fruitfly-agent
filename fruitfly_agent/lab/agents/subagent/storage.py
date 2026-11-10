"""Validated child indexes and content-addressed results over Core Session."""
from dataclasses import asdict
import json
from pathlib import Path
from fruitfly_agent.core.session import Session
from .contracts import ExecutionIdentity

STATES = {'queued', 'running', 'cancelling', 'completed', 'failed', 'cancelled', 'timed_out', 'interrupted'}

class SubagentStore:
    def __init__(self, root, artifacts, *, index=None):
        self.root = Path(root)
        self.artifacts = artifacts
        self.owns_index = index is None
        self.index = index if index is not None else Session(self.root / 'index.jsonl')
        self.rows = {}
        self.closed = False
        try:
            for entry in self.index.read_all():
                payload = entry.payload
                if not self.owns_index and (entry.type != 'meta' or payload.get('kind') not in {'subagent', 'subagent-message'}):
                    continue
                if entry.type == 'meta' and payload.get('kind') == 'subagent-message' and payload.get('schema') == 1:
                    ExecutionIdentity('message', payload['agent_id'], payload['run_id'])
                    continue
                if entry.type != 'meta' or payload.get('kind') != 'subagent' or payload.get('schema') != 1:
                    raise ValueError('invalid subagent index entry')
                row = payload['record']
                self.validate(row)
                self.rows[row['run_id']] = dict(row)
                if row.get('result_reference'):
                    self.read_result(row)
            for row in tuple(self.rows.values()):
                if row['state'] in {'queued', 'running', 'cancelling'}:
                    self.save({**row, 'state': 'interrupted', 'cleanup': 'failed',
                        'error': 'host_interrupted', 'activity': 'interrupted'})
        except BaseException:
            if self.owns_index:
                self.index.close()
            raise

    @staticmethod
    def validate(row):
        ExecutionIdentity(row['scope_id'], row['agent_id'], row['run_id'])
        if row.get('state') not in STATES or row.get('cleanup') not in {'pending', 'confirmed', 'failed'}:
            raise ValueError('invalid subagent state')
        if not isinstance(row.get('task'), str) or not isinstance(row.get('delivered'), bool):
            raise ValueError('invalid subagent record')

    def save(self, row):
        self.validate(row)
        frozen = json.loads(json.dumps(row, allow_nan=False))
        self.index.append('meta', {'kind': 'subagent', 'schema': 1, 'record': frozen}, sync=True)
        self.rows[row['run_id']] = frozen

    def result(self, row, payload):
        reference = self.artifacts.put_text(json.dumps({'identity': {
            key: row[key] for key in ('scope_id', 'agent_id', 'run_id')}, 'result': payload}, allow_nan=False)).artifact_id
        return reference

    def read_result(self, row):
        reference = row.get('result_reference')
        if not reference:
            return None
        value = json.loads(self.artifacts.read_text(reference))
        if value.get('identity') != {key: row[key] for key in ('scope_id', 'agent_id', 'run_id')}:
            raise ValueError('subagent result identity mismatch')
        return value['result']

    def close(self):
        if self.owns_index and not self.closed:
            self.index.close()
        self.closed = True
