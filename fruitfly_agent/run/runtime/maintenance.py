"""Host registered maintenance workers; algorithms never acquire activation authority."""
import asyncio
from datetime import datetime, timezone
import json

from fruitfly_agent.improvement.contracts.versions import content_hash, canonical_json
from fruitfly_agent.improvement.contracts.optimization import RetainedDocuments


class RetainedRuntimeService:
    def __init__(self, *, session, session_id, components, store, enabled=True, conditions_id='', emit_activity=None):
        self.session, self.session_id, self.store = session, session_id, store
        self.targets = {value.library_id: value for value in components.values()
            if isinstance(value, RetainedDocuments)}
        self.collections = {target.kind: target for target in self.targets.values()}
        if len(self.collections) != len(self.targets):
            raise ValueError('retained collection kinds must have a unique active owner')
        self.registered_workers = tuple(components.get('maintenance-workers', ()))
        # Worker availability controls both observation and explicit user runs.
        # Automatic scheduling is an independent policy gate.
        self.workers = self.registered_workers
        self.auto_enabled = enabled
        self.emit_activity = emit_activity
        self.task = None
        self.error = ''
        self.conditions_id = conditions_id

    def activate(self):
        self.workers = self.registered_workers
        self.auto_enabled = any(getattr(worker, 'auto_enabled', True) for worker in self.workers)

    def observe(self, *, completed):
        if not self.workers:
            return
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
        texts = {}
        for item in self.session.context_items():
            identity = self.session_id + ':' + item.id
            if item.message.role != 'user':
                continue
            content = item.message.content
            text = content if isinstance(content, str) else '\n'.join(
                block.text for block in content if getattr(block, 'type', '') == 'text')
            reference = content_hash(text)
            texts[reference] = text
            rows.append({'identity': identity,
                'session_id': self.session_id, 'message_id': item.id, 'artifact': reference,
                'chars': len(text), 'completed': outcomes.get(item.id, False)})
        if rows:
            stores = {id(store): store for worker in self.workers
                for store in (self.store.store_for(worker.library_id),)}
            for store in stores.values():
                for text in texts.values():
                    store.artifacts.put_text(text)
                store.observe(rows)

    async def run(self, *, manual=False, operation_id=None):
        if self.task is not None:
            return 'already-running'
        if not manual and not any(getattr(worker, 'auto_enabled', True) for worker in self.workers):
            return
        self.task = asyncio.current_task()
        self.error = ''
        outcome = 'no-work'
        try:
            if not self.workers:
                return
            for worker in self.workers:
                if not manual and not getattr(worker, 'auto_enabled', True):
                    continue
                store = self.store.store_for(worker.library_id)
                with store.maintenance_lease() as acquired:
                    if not acquired:
                        outcome = 'busy'
                        continue
                    first = True
                    while await self._run_worker(worker, store, manual=manual and first, operation_id=operation_id):
                        outcome = 'completed'
                        if operation_id is not None:
                            return outcome
                        first = False
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = type(exc).__name__ + ': ' + str(exc)
        finally:
            self.task = None
        return outcome

    async def _run_worker(self, worker, store, *, manual=False, operation_id=None):
        checkpoint = store.read()
        target = self.targets[worker.library_id]
        documents = store.library(worker.library_id) or target.retained_documents
        outstanding = [(identity, row) for identity, row in checkpoint['operations'].items()
            if (operation_id is None or identity == operation_id)
            if row['status'] not in {'completed', 'discarded'} and row.get('request_id')]
        if operation_id is not None and not outstanding:
            raise ValueError('the requested maintenance operation is not resumable')
        if outstanding:
            identity, record = outstanding[-1]
            if 'journal' not in record:
                raise ValueError('legacy maintenance operation has no recovery journal; end it before starting a new batch')
            journal = store.read_journal(record)
            if journal['conditions_id'] != self.conditions_id:
                raise ValueError('saved maintenance execution conditions differ from the active runtime')
            request = journal['request']
            captured = journal['checkpoint']
            initial = store.artifacts.read_text(captured['libraries'][worker.library_id]) if worker.library_id in captured['libraries'] else canonical_json(request['entries'])
            proposed = worker.request(captured, initial, manual=bool(request.get('manual', False)))
            if proposed is None or proposed['request_id'] != request['request_id']:
                raise ValueError('saved maintenance inputs differ from the active owner configuration')
            if checkpoint['libraries'].get(worker.library_id) != captured['libraries'].get(worker.library_id):
                raise ValueError('saved maintenance base changed; discard the failed batch before generating against the new revision')
            journal = store.resume(identity)
            checkpoint = captured
        else:
            request = worker.request(checkpoint, documents, manual=manual)
            if request is None:
                return False
            # Journal only the input facts and compact prior outcomes. Previous
            # journal references are independent retained operations.
            checkpoint['operations'] = {k: {field: value for field, value in row.items() if field != 'journal'}
                for k, row in checkpoint['operations'].items()}
            checkpoint['libraries'] = {key: ref for key, ref in checkpoint['libraries'].items() if key == worker.library_id}
            identity = store.begin(request['operation'], request['request_id'], request=request,
                checkpoint=checkpoint, conditions_id=self.conditions_id)
            journal = store.read_journal(store.read()['operations'][identity])
        position = 0
        call_started = False

        def on_call():
            nonlocal call_started
            call_started = True
            journal['calls'][position]['started'] = True
            store.record_journal(identity, journal)

        async def call(instructions, prompt, generate):
            nonlocal position, call_started
            digest = content_hash(canonical_json({'instructions': instructions, 'prompt': prompt}))
            if position < len(journal['calls']):
                saved = journal['calls'][position]
                if saved['input'] != digest or 'response' not in saved:
                    raise ValueError('saved maintenance call differs from reconstructed input')
                response = store.artifacts.read_text(saved['response'])
            else:
                journal['calls'].append({'input': digest, 'started': False})
                store.record_journal(identity, journal)
                response = await generate()
                journal['calls'][position]['response'] = store.artifacts.put_text(response).artifact_id
                store.record_journal(identity, journal)
            call_started = False
            position += 1
            return response

        try:
            async def activity(phase, *, batch=0, total=0, text=''):
                if self.emit_activity is not None:
                    result = self.emit_activity(phase=phase, subject=worker.library_id,
                        batch=batch, total=total, text=text)
                    if hasattr(result, '__await__'):
                        await result
            async with asyncio.timeout(worker.config.timeout_seconds):
                text, processed, turns = await worker.generate(request, checkpoint,
                    lambda row: store.artifacts.read_text(row['artifact']), on_call=on_call,
                    call=call, on_activity=activity if self.emit_activity is not None else None,
                    observed_at=journal['observed_at'])
            if text is not None:
                target.validate_documents(json.loads(text))
            store.finish(identity, status='completed', key=worker.library_id, text=text,
                parent=checkpoint['libraries'].get(worker.library_id), processed=processed, turns=turns,
                publish=True)
            return True
        except asyncio.CancelledError:
            store.finish(identity, status='unknown' if call_started else 'cancelled')
            raise
        except Exception:
            store.finish(identity, status='unknown' if call_started else 'failed')
            raise

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
            return {'entries': [], 'pending': [], 'error': self.error if kind == 'memory' else ''}
        if kind != 'memory':
            state = self.store.store_for(target.library_id).read()
            return {'entries': target.view_entries(), 'pending': [dict(row, id=identity)
                for identity, row in state['pending'].items()
                if row['status'] == 'pending' and row['key'] == target.library_id], 'error': ''}
        # The visible active runtime remains frozen until its next checked rebuild.
        key = target.library_id
        entries = target.view_entries()
        state = self.store.store_for(key).read()
        worker = next((item for item in self.workers if item.library_id == key), None)
        automatic_enabled = bool(worker is not None and getattr(worker, 'auto_enabled', True))
        automatic_due = bool(worker is not None and worker.request(state,
            self.store.store_for(key).library(key) or target.retained_documents) is not None)
        unresolved = [dict(row, id=identity) for identity, row in state['operations'].items()
            if row['status'] not in {'completed', 'discarded'}]
        blocked = bool(unresolved)
        return {'entries': entries, 'pending': [dict(v, id=k) for k, v in state['pending'].items()
            if v['status'] == 'pending' and v['key'] == key], 'error': self.error,
            'operations': [dict(row, id=identity, recoverable='journal' in row) for identity, row in state['operations'].items()
                if row['status'] in {'running', 'unknown', 'failed', 'retry-authorized', 'retry-generation'}],
            'saved_revision': state['libraries'].get(key, ''),
            'loaded_revision': content_hash(target.retained_documents),
            'refresh_pending': key in state['libraries'] and state['libraries'][key] != content_hash(target.retained_documents),
            'user_chars': sum(e['chars'] for e in state['evidence'][state['processed']:]),
            'user_turns': sum(e['completed'] for e in state['evidence']) - state['consolidated_turns'],
            'memory_path': str(getattr(self.store.store_for(key), 'root', '')),
            'auto_enabled': automatic_enabled,
            'automatic_due': automatic_due,
            'blocked': blocked,
            'can_run_manually': bool(self.workers)}

    def read_document(self, kind, identity):
        target = self.collections.get(kind)
        if target is None:
            raise ValueError('retained document identity is unavailable')
        return target.read_entry(identity)

    def review(self, identity, action):
        if action == 'discard':
            row = self.store.read()['operations'].get(identity)
            if row is not None and 'journal' not in row:
                return self.store.end_legacy_operation(identity)
            return self.store.discard(identity)
        if action == 'import':
            return self.store.import_workspace(identity, validators={key: target.validate_documents
                for key, target in self.targets.items()})
        if action == 'retry':
            if not self.workers:
                raise ValueError('no maintenance worker is enabled')
            return self.store.allow_retry(identity)
        if action == 'run':
            raise ValueError('manual maintenance must be started through the interactive application')
        row = self.store.read()['pending'].get(identity)
        if row is None or row['key'] not in self.targets:
            raise ValueError('retained update is unavailable in this runtime')
        self.targets[row['key']].validate_documents(json.loads(self.store.artifacts.read_text(row['artifact'])))
        return self.store.review(identity, action)
