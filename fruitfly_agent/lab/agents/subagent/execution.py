"""Independent Core invocation over resources explicitly prepared by a host."""
from dataclasses import replace
import hashlib
import asyncio
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.data_model import CustomMessage, UserMessage
from fruitfly_agent.core.extensions.hooks import BEFORE_REQUEST, BEFORE_TOOL, AFTER_TOOL, AFTER_RESPONSE, HookRegistry
from fruitfly_agent.core.errors import FatalError
from fruitfly_agent.core.context.budget import forward_context_capabilities

class ChildExecution:
    def __init__(self, runtime, *, request_limit, instructions):
        self.runtime = runtime
        self.request_limit = request_limit
        self.instructions = instructions
        self.pending = []
        self.offered_messages = []
        self.message_ids = set()
        self.requests = 0
        self.request_limit_reached = False
        self.responses = 0
        self.complete_usage = True
        self.initial_messages = 0
        self.accepting_input = True
        self.closed = False
        self.on_activity = lambda phase, requests: None

    def can_steer(self, text):
        return not self.closed and self.accepting_input and sum(len(item[1]) for item in self.pending) + len(text) <= 16000

    def steer(self, message_id, text):
        if message_id in self.message_ids:
            return
        if not self.can_steer(text):
            raise ValueError('child execution is closed')
        self.message_ids.add(message_id)
        self.pending.append((message_id, text))

    async def run(self, request, *, signal):
        if self.closed:
            raise ValueError('child execution is closed')
        session = self.runtime.config.session
        self.initial_messages = len(session.canonical_messages())
        message = UserMessage(request.task + ('\n\nContext:\n' + request.context if request.context else ''))
        session.append('message', {'message': message.to_dict()}, sync=True)
        hooks = self.runtime.config.hooks.clone() if self.runtime.config.hooks else HookRegistry(session=session)
        self.requests = 0
        def count(event):
            durable = session.canonical_messages() if self.offered_messages else ()
            for message_id in self.offered_messages:
                if not any(isinstance(m, CustomMessage) and m.kind == 'agent-message' and m.text.startswith('Parent agent message ' + message_id + ':') for m in durable):
                    raise FatalError('parent message was not committed to child history')
                session.append('meta', {'kind': 'parent-message-delivered', 'message_id': message_id,
                    'run_id': request.identity.run_id}, sync=True)
            self.offered_messages.clear()
            if self.requests >= self.request_limit:
                self.request_limit_reached = True
                raise FatalError('subagent model request limit reached')

        def receipt(event):
            self.responses += 1
            self.complete_usage = self.complete_usage and event.assistant.usage is not None
        hooks.add(AFTER_RESPONSE, receipt)
        hooks.add(BEFORE_REQUEST, count, required=True, priority=-1000)
        hooks.add(BEFORE_TOOL, lambda event: self.on_activity('preparing_tool', self.requests))
        hooks.add(AFTER_TOOL, lambda event: self.on_activity('model', self.requests))
        def drain(ctx):
            messages = []
            while self.pending:
                message_id, text = self.pending.pop(0)
                self.offered_messages.append(message_id)
                messages.append(CustomMessage('agent-message',
                    'Parent agent message ' + message_id + ':\n' + text))
            return messages
        def provider(view, *, signal=None):
            if self.requests >= self.request_limit:
                self.request_limit_reached = True
                raise FatalError('subagent model request limit reached')
            self.requests += 1
            self.on_activity('model', self.requests)
            return self.runtime.config.provider(view, signal=signal)
        forward_context_capabilities(provider, self.runtime.config.provider)
        config = replace(self.runtime.config, provider=provider, hooks=hooks,
            system_prompt=self.runtime.config.system_prompt + '\n\n' + self.instructions,
            get_steering_messages=drain, get_follow_up_messages=drain)
        session.append('meta', {'kind': 'child-execution', 'scope_id': request.identity.scope_id,
            'agent_id': request.identity.agent_id, 'run_id': request.identity.run_id,
            'instructions': self.instructions, 'system_prompt_hash': 'sha256:' + hashlib.sha256(config.system_prompt.encode()).hexdigest(),
            'max_model_requests': self.request_limit}, sync=True)
        try:
            return await run_agent_loop(config, session.messages(), signal=signal,
                context_pipeline=self.runtime.context_pipeline)
        finally:
            self.accepting_input = False

    @property
    def usage_known(self):
        return self.complete_usage and self.responses == self.requests

    async def close(self):
        if not self.closed:
            await self.runtime.close()
            self.closed = True
