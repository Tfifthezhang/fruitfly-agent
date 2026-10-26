"""Explicit per-runtime external tool grants, separate from file permissions."""
import hashlib
import json
import uuid
from contextlib import asynccontextmanager
from fruitfly_agent.core.tool_runtime.authorization import AuthorizationPrompt, AuthorizationDecision


class ExternalToolPolicy:
    def __init__(self, service, tool, identity):
        self.service, self.tool = service, tool
        self.scope = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    @asynccontextmanager
    async def authorize(self, request, confirm, signal=None):
        if request.permission is None or request.permission.operation != 'external_tool':
            yield AuthorizationDecision(False, 'external tool declaration differs from authorization')
            return
        prompt = AuthorizationPrompt(uuid.uuid4().hex, request.tool_name,
            'external-tool:' + self.scope + ':' + request.tool_name, (),
            f'External service: {self.service}; tool: {self.tool}\n'
            'The service runs locally with its own OS permissions; this grant is not a sandbox.\n'
            + json.dumps(request.arguments, ensure_ascii=False, sort_keys=True),
            'Allow this external tool for this runtime session')
        answer = await confirm(prompt, signal)
        yield AuthorizationDecision(answer in {'once', 'session'}, 'external tool ' + answer)
