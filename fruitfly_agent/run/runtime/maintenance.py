"""Host registered maintenance workers; algorithms never acquire activation authority."""
import asyncio
from datetime import datetime, timezone
import json

from fruitfly_agent.improvement.contracts.versions import content_hash, canonical_json
from fruitfly_agent.improvement.contracts.optimization import RetainedDocuments


class RetainedRuntimeService:
    def __init__(self, *, session, session_id, components, store, enabled=True):
        self.session, self.session_id, self.store = session, session_id, store
        self.targets = {value.library_id: value for value in components.values()
            if isinstance(value, RetainedDocuments)}
        self.collections = {target.kind: target for target in self.targets.values()}
        if len(self.collections) != len(self.targets):
            raise ValueError('retained collection kinds must have a unique active owner')
        self.registered_workers = tuple(components.get('maintenance-workers', ()))
        self.workers = self.registered_workers if enabled else ()
        self.task = None
        self.error = ''

    def activate(self):
        self.workers = self.registered_workers

    def observe(self, *, completed):
        if not self.workers:
            return
        known = {row['identity'] for row in self.store.read()['evidence']}
        # Read canonical run boundaries, so a crash followed by a successful run
        # cannot turn older interrupted inputs into completed user turns.
        outcomes, active, last_user, run_id = {}, [], None, None
        for entry in self.session.read_all():
            if entry.type == 'message' and entry.payload.get('message', {}).get('role') == 'user':
                last_user = 'session:' + str(entry.id)
                outcomes[last_user] = False
                if run_id is not None:
                    active.append(last_user)
            elif entry.type == 'meta' and entry.payload.get('kind') == 'runRecord':
                record = entry.payload
                if record['event'] == 'start':
                    run_id = record['run_id']
                    active = [last_user] if last_user else []
                elif record['event'] == 'end' and record['run_id'] == run_id:
                    data = record['data']
                    success = not data.get('is_error') and data.get('stop_reason') not in {'error', 'aborted', 'cancelled'}
                    for identity in active:
                        outcomes[identity] = success
                    active, run_id = [], None
        rows = []
        for item in self.session.context_items():
            identity = self.session_id + ':' + item.id
            if item.message.role != 'user' or identity in known:
                continue
            content = item.message.content
            text = content if isinstance(content, str) else '\n'.join(
                block.text for block in content if getattr(block, 'type', '') == 'text')
            reference = self.store.artifacts.put_text(text).artifact_id
            rows.append({'identity': identity,
                'session_id': self.session_id, 'message_id': item.id, 'artifact': reference,
                'chars': len(text), 'completed': outcomes.get(item.id, False)})
        if rows:
            self.store.observe(rows)

    async def run(self):
        if self.task is not None:
            return
        self.task = asyncio.current_task()
        self.error = ''
        try:
            for worker in self.workers:
                checkpoint = self.store.read()
                documents = self.targets[worker.library_id].retained_documents
                request = worker.request(checkpoint, documents)
                if request is None:
                    continue
                identity = self.store.begin(request['operation'], request['request_id'])
                try:
                    async with asyncio.timeout(worker.config.timeout_seconds):
                        text, processed, turns = await worker.generate(request, checkpoint,
                            lambda row: self.store.artifacts.read_text(row['artifact']))
                    if text is not None:
                        # Revalidate through the owner before anything becomes reviewable.
                        self.targets[worker.library_id].validate_documents(json.loads(text))
                    self.store.finish(identity, status='completed', key=worker.library_id, text=text,
                        parent=checkpoint['libraries'].get(worker.library_id), processed=processed, turns=turns)
                except asyncio.CancelledError:
                    self.store.finish(identity, status='unknown')
                    raise
                except ValueError:
                    self.store.finish(identity, status='failed')
                    raise
                except Exception:
                    # A request may have reached a model before a transport failure.
                    self.store.finish(identity, status='unknown')
                    raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = type(exc).__name__ + ': ' + str(exc)
        finally:
            self.task = None

    def cancel(self):
        if self.task is None:
            return False
        self.task.cancel()
        return True

    async def close(self):
        task = self.task
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def describe(self, kind):
        target = self.collections.get(kind)
        if target is None:
            return {'entries': [], 'pending': [], 'error': self.error}
        # The visible active runtime remains frozen until its next checked rebuild.
        key = target.library_id
        entries = target.view_entries()
        state = self.store.read()
        return {'entries': entries, 'pending': [dict(v, id=k) for k, v in state['pending'].items()
            if v['status'] == 'pending' and v['key'] == key], 'error': self.error,
            'operations': [dict(row, id=identity) for identity, row in state['operations'].items()
                if row['status'] in {'running', 'unknown'}],
            'user_chars': sum(e['chars'] for e in state['evidence'][state['processed']:]),
            'user_turns': sum(e['completed'] for e in state['evidence']) - state['consolidated_turns']}

    def read_document(self, kind, identity):
        target = self.collections.get(kind)
        if target is None:
            raise ValueError('retained document identity is unavailable')
        return target.read_entry(identity)

    def review(self, identity, action):
        if action == 'retry':
            if not self.workers:
                raise ValueError('no maintenance worker is enabled')
            self.error = ''
            return self.store.allow_retry(identity)
        row = self.store.read()['pending'].get(identity)
        if row is None or row['key'] not in self.targets:
            raise ValueError('retained update is unavailable in this runtime')
        self.targets[row['key']].validate_documents(json.loads(self.store.artifacts.read_text(row['artifact'])))
        return self.store.review(identity, action)
