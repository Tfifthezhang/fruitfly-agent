"""Bounded parent-owned delegation with durable results and explicit retirement."""
import asyncio
from dataclasses import replace, asdict
import inspect
import json
import math
import time
from uuid import uuid4
from fruitfly_agent.core.data_model import AssistantMessage, CustomMessage, ToolResultMessage
from fruitfly_agent.core.extensions.hooks import BEFORE_REQUEST, HookRegistry
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.errors import FatalError
from fruitfly_agent.core.extensions.operations import OperationSupervisor, OperationCleanupError
from .contracts import ChildRequest, ExecutionIdentity
from fruitfly_agent.lab.catalog.agent_runtime import AgentRuntimeError
from .execution import ChildExecution
from .views import bounded

ACTIVE = {'queued', 'running', 'cancelling'}

class SubagentError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code

class SubagentService:
    def __init__(self, prepare, store, *, max_concurrent=2, max_agents=8,
                 run_timeout_seconds=600, max_model_requests=64, instructions='', retirement_timeout=10):
        for value in (max_concurrent, max_agents, max_model_requests):
            if type(value) is not int or value < 1:
                raise ValueError('subagent limits must be positive integers')
        if isinstance(run_timeout_seconds, bool) or not isinstance(run_timeout_seconds, (int, float)) or not math.isfinite(run_timeout_seconds) or run_timeout_seconds <= 0:
            raise ValueError('subagent timeout must be finite and positive')
        OperationSupervisor(retirement_timeout=retirement_timeout)
        self.prepare, self.store = prepare, store
        self.max_concurrent, self.max_agents = max_concurrent, max_agents
        self.timeout, self.request_limit = run_timeout_seconds, max_model_requests
        self.instructions, self.retirement_timeout = instructions, retirement_timeout
        self.scope_id = None
        self.signal = None
        self.tasks, self.signals, self.executions = {}, {}, {}
        self.requests = {}
        self.agents = set()
        self.receipts = {}
        self.offered_results = {}
        self.slots = asyncio.Semaphore(max_concurrent)
        self.changed = asyncio.Event()
        self.revision = 0
        self.unconfirmed = set()
        self.closed = False
        self.poisoned = False

    def _poison(self):
        self.poisoned = True
        for signal in self.signals.values():
            signal.set()

    def begin(self, signal=None):
        if self.closed or self.poisoned:
            raise SubagentError('scope_closed')
        if self.scope_id is not None:
            raise SubagentError('scope_busy')
        self.scope_id = uuid4().hex
        self.signal = signal
        self.agents = set()
        self.receipts.clear()
        self.offered_results.clear()

    def _admit(self):
        if self.closed or self.poisoned or self.scope_id is None or (self.signal is not None and self.signal.is_set()):
            raise SubagentError('scope_closed')

    def _save(self, row):
        try:
            self.store.save(row)
        except BaseException:
            self._poison()
            raise
        self.revision += 1
        self.changed.set()

    def _row(self, agent_id, run_id):
        row = self.store.rows.get(run_id)
        if row is None or row['agent_id'] != agent_id:
            raise SubagentError('unknown_agent')
        return row

    def _current(self, agent_id, run_id):
        self._admit()
        row = self._row(agent_id, run_id)
        if row['scope_id'] != self.scope_id:
            raise SubagentError('scope_closed')
        latest = next(r for r in reversed(tuple(self.store.rows.values())) if r['agent_id'] == agent_id)
        if latest['run_id'] != run_id:
            raise SubagentError('stale_run')
        return row

    def spawn(self, task, context=''):
        self._admit()
        if len(self.agents) >= self.max_agents:
            raise SubagentError('capacity_exceeded')
        assert self.scope_id is not None
        agent_id = uuid4().hex
        identity = ExecutionIdentity(self.scope_id, agent_id, uuid4().hex)
        request = ChildRequest(identity, task, context)
        self.agents.add(agent_id)
        return self._launch(request)

    def _launch(self, request):
        identity = request.identity
        row = dict(scope_id=identity.scope_id, agent_id=identity.agent_id, run_id=identity.run_id,
            task=request.task, state='queued', cleanup='pending', activity='queued',
            created_at=time.time(), started_at=None, ended_at=None, elapsed_seconds=None,
            model='', model_profile='', result_reference=None, summary='', error=None,
            input_tokens=None, output_tokens=None, model_requests=0, tool_calls=0, delivered=False,
            result_resource=getattr(self, 'result_prefix', '') + identity.agent_id + '/' + identity.run_id)
        self._save(row)
        self.requests[identity.run_id] = request
        self.signals[identity.run_id] = asyncio.Event()
        self.tasks[identity.run_id] = asyncio.create_task(self._work(request), name='subagent:' + identity.run_id)
        return dict(row)

    def send(self, agent_id, run_id, mode, message):
        row = self._current(agent_id, run_id)
        if not isinstance(message, str) or not message.strip() or len(message) > 16000:
            raise SubagentError('invalid_message')
        if mode == 'followup':
            if row['state'] in ACTIVE:
                raise SubagentError('agent_busy')
            if row['cleanup'] != 'confirmed':
                raise SubagentError('cleanup_failed')
            assert self.scope_id is not None
            return self._launch(ChildRequest(ExecutionIdentity(self.scope_id, agent_id, uuid4().hex), message))
        if mode != 'steer' or row['state'] not in {'queued', 'running'}:
            raise SubagentError('invalid_state')
        message_id = uuid4().hex
        # Canonical message admission is durable before acknowledgement. Core
        # receives it on its next request; the session is the sole message source.
        self.executions_pending(agent_id, run_id, message_id, message)
        return {'agent_id': agent_id, 'run_id': run_id, 'message_id': message_id, 'accepted': True}

    def executions_pending(self, agent_id, run_id, message_id, message):
        request = self.requests[run_id]
        runtime = self.executions.get(agent_id)
        amended = replace(request, context=request.context + '\nParent message ' + message_id + ': ' + message) if runtime is None else None
        if runtime is not None and not runtime.can_steer(message):
            raise SubagentError('invalid_state')
        try:
            self.store.index.append('meta', {'kind': 'subagent-message', 'schema': 1,
                'agent_id': agent_id, 'run_id': run_id, 'message_id': message_id, 'text': message}, sync=True)
        except BaseException:
            self._poison()
            raise
        if runtime is not None:
            runtime.steer(message_id, message)
        else:
            self.requests[run_id] = amended

    async def _work(self, request):
        run_id, agent_id = request.identity.run_id, request.identity.agent_id
        signal = self.signals[run_id]
        started = time.monotonic()
        supervisor = OperationSupervisor(retirement_timeout=self.retirement_timeout)
        acquired = False
        async def invoke():
            nonlocal acquired
            await self.slots.acquire()
            acquired = True
            if self.poisoned or self.closed or request.identity.scope_id != self.scope_id:
                raise SubagentError('scope_closed')
            runtime = self.executions.get(agent_id)
            if runtime is None:
                prepared = await self.prepare(request)
                runtime = ChildExecution(prepared, request_limit=self.request_limit, instructions=self.instructions)
                self.executions[agent_id] = runtime
                runtime.on_activity = lambda phase, requests: self._save({**self.store.rows[run_id], 'activity': phase, 'model_requests': requests})
                await prepared.start()
            row = self.store.rows[run_id]
            self._save({**row, 'state': 'running', 'activity': 'model', 'started_at': time.time(),
                'model': runtime.runtime.config.model,
                'model_profile': runtime.runtime.manifest.get('model_profile', '')})
            result = await runtime.run(self.requests[run_id], signal=signal)
            return result
        state, error, result = 'failed', None, None
        try:
            result = await supervisor.run(invoke, timeout=self.timeout, signal=signal)
            state = 'failed' if result.is_error else 'cancelled' if result.stop_reason == 'aborted' else 'completed'
            if result.diagnostics and result.diagnostics.termination_reason not in {'model_complete', 'cancelled'}:
                state, error = 'failed', result.diagnostics.termination_reason
            if result.is_error:
                runtime = self.executions.get(agent_id)
                error = 'model_request_limit' if runtime and runtime.request_limit_reached else 'execution_failed'
        except asyncio.CancelledError:
            state = 'cancelled'
        except TimeoutError:
            state, error = 'timed_out', 'execution_deadline'
        except OperationCleanupError:
            self.unconfirmed.add(agent_id)
            error = 'cleanup_failed'
            self._poison()
        except Exception as exc:
            error = exc.code if isinstance(exc, AgentRuntimeError) else type(exc).__name__
        finally:
            runtime = self.executions.get(agent_id)
            requests = runtime.requests if runtime else 0
            if runtime is not None and not supervisor.poisoned:
                closer = OperationSupervisor(retirement_timeout=self.retirement_timeout)
                try:
                    await closer.run(runtime.close, timeout=self.retirement_timeout)
                    self.executions.pop(agent_id, None)
                except BaseException:
                    self._poison()
                    self.unconfirmed.add(agent_id)
                    error = 'cleanup_failed'
            row = self.store.rows[run_id]
            summary = ''
            if result is not None:
                current_messages = result.canonical_messages[runtime.initial_messages:] if runtime else ()
                summary = next((m.text for m in reversed(current_messages) if isinstance(m, AssistantMessage)), '')
            payload = {'state': state, 'output': summary, 'error': error,
                'usage': result.usage.to_dict() if result and runtime and runtime.usage_known else None,
                'diagnostics': asdict(result.diagnostics) if result and result.diagnostics else None}
            try:
                reference = self.store.result(row, payload)
                self._save({**row, 'state': state, 'activity': state, 'error': error,
                    'summary': summary[:4000], 'result_reference': reference,
                    'ended_at': time.time(), 'elapsed_seconds': time.monotonic() - started,
                    'cleanup': 'failed' if agent_id in self.unconfirmed else 'confirmed',
                    'model_requests': requests,
                    'tool_calls': result.tool_call_count if result else 0,
                    'input_tokens': result.usage.input_tokens if result and runtime and runtime.usage_known else None,
                    'output_tokens': result.usage.output_tokens if result and runtime and runtime.usage_known else None})
            except Exception:
                self._poison()
                self.changed.set()
            finally:
                if acquired and agent_id not in self.unconfirmed:
                    self.slots.release()

    async def wait(self, refs, *, mode='all', timeout_seconds=30, signal=None, deliver=False):
        if mode not in {'all', 'any'} or isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or not 0 <= timeout_seconds <= 60:
            raise SubagentError('invalid_wait')
        if not refs or len(refs) > self.max_agents:
            raise SubagentError('invalid_wait')
        for agent_id, run_id in refs:
            self._row(agent_id, run_id)
        def ready():
            terminal = [self.store.rows[r]['state'] not in ACTIVE for _, r in refs]
            return all(terminal) if mode == 'all' else any(terminal)
        deadline = time.monotonic() + timeout_seconds
        while not ready():
            if self.poisoned:
                raise SubagentError('cleanup_failed')
            if signal is not None and signal.is_set():
                raise asyncio.CancelledError
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self.changed.clear()
            change = asyncio.create_task(self.changed.wait())
            abort = asyncio.create_task(signal.wait()) if signal is not None else None
            try:
                await asyncio.wait((change, abort) if abort else (change,), timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
            finally:
                change.cancel()
                if abort:
                    abort.cancel()
                await asyncio.gather(change, *((abort,) if abort else ()), return_exceptions=True)
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        values = []
        for agent_id, run_id in refs:
            row = self._row(agent_id, run_id)
            if deliver and row['state'] not in ACTIVE and not row['delivered']:
                self._save({**row, 'delivered': True})
            values.append(dict(self.store.rows[run_id]))
        return {'timed_out': not ready(), 'executions': values}

    async def cancel(self, agent_id, run_id):
        row = self._current(agent_id, run_id)
        if row['state'] not in ACTIVE:
            return dict(row)
        self._save({**row, 'state': 'cancelling', 'activity': 'cancelling'})
        self.signals[run_id].set()
        done, _ = await asyncio.wait((self.tasks[run_id],), timeout=self.retirement_timeout + 1)
        if not done:
            self.unconfirmed.add(agent_id)
            self._poison()
            raise SubagentError('cleanup_failed')
        return dict(self.store.rows[run_id])

    def snapshot(self):
        return {'enabled': True, 'revision': self.revision, 'max_concurrent': self.max_concurrent,
            'scope_id': self.scope_id, 'poisoned': self.poisoned,
            'executions': tuple(dict(v) for v in self.store.rows.values())}

    def detail(self, agent_id, run_id=None):
        rows = [r for r in self.store.rows.values() if r['agent_id'] == agent_id and (run_id is None or r['run_id'] == run_id)]
        if not rows:
            raise SubagentError('unknown_agent')
        return dict(rows[-1])

    async def end(self):
        self.scope_id = None
        for signal in self.signals.values():
            signal.set()
        pending = tuple(t for t in self.tasks.values() if not t.done())
        if pending:
            _, left = await asyncio.wait(pending, timeout=self.retirement_timeout + 1)
            if left:
                self._poison()
                self.unconfirmed.update(self.requests[run_id].identity.agent_id for run_id, task in self.tasks.items() if task in left)
        for agent_id, execution in tuple(self.executions.items()):
            if agent_id in self.unconfirmed:
                continue
            supervisor = OperationSupervisor(retirement_timeout=self.retirement_timeout)
            try:
                await supervisor.run(execution.close, timeout=self.retirement_timeout)
            except BaseException:
                self._poison()
        if not self.unconfirmed:
            self.executions.clear()
        self.signal = None
        if not any(not task.done() for task in self.tasks.values()):
            self.tasks.clear()
            self.signals.clear()
            self.requests.clear()
        if self.poisoned:
            raise OperationCleanupError('subagent resources could not be confirmed retired')

    async def close(self):
        self.closed = True
        try:
            await self.end()
        finally:
            self.store.close()

    async def run_loop(self, config, messages, *, signal=None, context_pipeline=None):
        self.begin(signal)
        previous_steer, previous_follow = config.get_steering_messages, config.get_follow_up_messages
        async def inherited(callback, context):
            value = callback(context) if callback else []
            return await value if inspect.isawaitable(value) else value
        def notices():
            output = []
            for row in tuple(self.store.rows.values()):
                if row['scope_id'] == self.scope_id and row['state'] not in ACTIVE and not row['delivered'] and row['run_id'] not in self.offered_results:
                    message = CustomMessage('subagent-result', 'Subagent execution result (derived agent output):\n' + json.dumps(bounded(row)))
                    self.offered_results[row['run_id']] = message
                    output.append(message)
            return output
        async def steering(context):
            return [*await inherited(previous_steer, context), *notices()]
        async def follow(context):
            while any(r['scope_id'] == self.scope_id and r['state'] in ACTIVE for r in self.store.rows.values()):
                refs = [(r['agent_id'], r['run_id']) for r in self.store.rows.values() if r['scope_id'] == self.scope_id and r['state'] in ACTIVE]
                await self.wait(refs, mode='any', signal=signal)
            extra = await inherited(previous_follow, context)
            return [*extra, *notices()]
        hooks = config.hooks.clone() if config.hooks else HookRegistry(session=config.session)
        def acknowledge(event):
            if not self.offered_results:
                return
            durable = config.session.canonical_messages() if config.session is not None else event.messages
            for run_id, offered in tuple(self.offered_results.items()):
                committed = offered in durable if isinstance(offered, CustomMessage) else any(
                    isinstance(message, ToolResultMessage) and message.tool_call_id == offered and not message.is_error
                    and run_id in message.text for message in durable)
                if committed:
                    self._save({**self.store.rows[run_id], 'delivered': True})
                    self.offered_results.pop(run_id, None)
                elif (isinstance(offered, CustomMessage) and offered in event.messages) or (isinstance(offered, str) and any(
                        isinstance(message, ToolResultMessage) and message.tool_call_id == offered for message in event.messages)):
                    raise FatalError('subagent result was not committed to parent history')
                elif isinstance(offered, str):
                    # A result hook may have removed/rejected a wait receipt.
                    # Make its authoritative result available by notification.
                    self.offered_results.pop(run_id, None)
        hooks.add(BEFORE_REQUEST, acknowledge, required=True, priority=-1000)
        try:
            result = await run_agent_loop(replace(config, hooks=hooks, get_steering_messages=steering,
                get_follow_up_messages=follow), messages, signal=signal, context_pipeline=context_pipeline)
            outstanding = any(r['scope_id'] == self.scope_id and (r['state'] in ACTIVE or not r['delivered']) for r in self.store.rows.values())
            if outstanding and result.stop_reason != 'aborted':
                result = replace(result, is_error=True, error_details={'kind': 'subagent_results_uncollected'})
            return result
        finally:
            await self.end()
