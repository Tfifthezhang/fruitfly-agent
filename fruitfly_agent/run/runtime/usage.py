"""Provider observations across main and auxiliary calls; no admission control."""
from pathlib import Path
from uuid import uuid4
import json
import os
import tempfile
import time

from fruitfly_agent.core.context.budget import forward_context_capabilities
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.providers.registry import ProviderRegistry


class ModelUsage:
    def __init__(self, *, receipt=None):
        self.requests = {}
        self.receipt = Path(receipt) if receipt else None
        self.write()

    @property
    def used(self):
        return len(self.requests)

    def begin(self, model):
        identity=uuid4().hex
        self.requests[identity]={'id':identity,'model':model,'status':'started','usage':None}
        self.write()
        return identity

    def finish(self, identity, *, status, usage=None, elapsed_seconds=None):
        self.requests[identity].update(status=status,usage=usage,elapsed_seconds=elapsed_seconds)
        self.write()

    def write(self):
        if self.receipt is None:return
        self.receipt.parent.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='.model-usage-',dir=self.receipt.parent)
        try:
            with os.fdopen(fd,'w') as out:
                json.dump({'schema_version':1,'used':self.used,'requests':list(self.requests.values())},out)
            os.replace(name,self.receipt)
        finally:
            Path(name).unlink(missing_ok=True)


class ObservedProvider:
    def __init__(self, provider, usage):
        self.provider,self.usage=provider,usage
        self.transport_parameters=getattr(provider,'transport_parameters',None)
        forward_context_capabilities(self,provider)

    def __call__(self,view,*,signal=None):
        identity,started=self.usage.begin(view.model),time.monotonic()
        async def events():
            inner=None
            try:
                inner=self.provider(view,signal=signal)
                async for event in inner:yield event
                message=await inner.result()
                self.usage.finish(identity,status='completed',usage=message.usage.to_dict() if message.usage else None,elapsed_seconds=time.monotonic()-started)
                yield StreamDone(message)
            except BaseException:
                self.usage.finish(identity,status='interrupted',elapsed_seconds=time.monotonic()-started)
                raise
            finally:
                if inner is not None:await inner.aclose()
        return AssistantMessageEventStream(events())

    async def aclose(self):
        close=getattr(self.provider,'aclose',None)
        if close is not None:await close()


class ObservedProviderRegistry(ProviderRegistry):
    def __init__(self,registry,usage):
        super().__init__()
        self.registry,self.usage=registry,usage

    def register(self,sdk,protocol,factory,*,default=False):
        self.registry.register(sdk,protocol,factory,default=default)

    def registered_pairs(self):return self.registry.registered_pairs()
    def sdk_for(self,protocol):return self.registry.sdk_for(protocol)
    def validate(self,spec):self.registry.validate(spec)
    def create(self,spec,env=None):return ObservedProvider(self.registry.create(spec,env),self.usage)
