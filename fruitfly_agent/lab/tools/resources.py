"""Run-local read-only resource routing, independent of the execution filesystem."""
import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4
from fruitfly_agent.core.tool_runtime.authorization import AuthorizationDecision, unrestricted_authorization

PREFIX = 'resource://'


def is_resource(path):
    return isinstance(path, str) and path.lstrip('@').startswith(PREFIX)


class ResourceRegistry:
    def __init__(self, *, scope=None):
        import hashlib
        self.scope = hashlib.sha256(scope.encode()).hexdigest() if scope else uuid4().hex
        self.providers = {}
        self.closed = False

    def mount(self, name, reader):
        if self.closed or name in self.providers or not name or '/' in name:
            raise ValueError('invalid or duplicate resource mount')
        prefix = f'{PREFIX}{self.scope}/{name}/'
        self.providers[name] = reader
        return prefix

    def read(self, reference):
        if self.closed:
            raise ValueError('resource scope is retired')
        prefix = f'{PREFIX}{self.scope}/'
        if not isinstance(reference, str) or not reference.startswith(prefix):
            raise ValueError('resource is outside this runtime')
        parts = reference[len(prefix):].split('/')
        if len(parts) < 2 or any(not p or p in {'.', '..'} or '%' in p or '\\' in p for p in parts):
            raise ValueError('invalid resource reference')
        if parts[0] not in self.providers:
            raise ValueError('resource owner is unavailable')
        data = self.providers[parts[0]]('/'.join(parts[1:]))
        if not isinstance(data, bytes):
            raise TypeError('resource reader must return bytes')
        return data

    def close(self):
        self.closed = True
        self.providers.clear()

    async def aclose(self):
        self.close()


class ResourceAuthorizer:
    def __init__(self, resources, delegate):
        self.resources, self.delegate = resources, delegate

    def __getattr__(self, name):
        if name == 'identity' and self.delegate is not None:
            return getattr(self.delegate, name)
        raise AttributeError(name)

    @asynccontextmanager
    async def authorize(self, request, *, signal=None):
        if signal is not None and signal.is_set():
            raise asyncio.CancelledError
        paths = [request.arguments.get(name) for name in request.permission.path_arguments] if request.permission else []
        references = [p.lstrip('@') for p in paths if is_resource(p)]
        if references:
            allowed = False
            if request.permission.operation == 'read' and len(paths) == len(references) == 1 and self.resources is not None:
                try:
                    self.resources.read(references[0])
                    allowed = True
                except (ValueError, KeyError, OSError):
                    pass
            yield AuthorizationDecision(allowed, 'registered read-only resource' if allowed else 'resource access denied')
            return
        scope = self.delegate.authorize(request, signal=signal) if self.delegate else unrestricted_authorization()
        async with scope as decision:
            yield decision
