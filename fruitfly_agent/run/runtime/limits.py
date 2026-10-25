"""Shared per-process request allowance across main and auxiliary Providers."""
from pathlib import Path
import json
import os
import tempfile
from fruitfly_agent.core.errors import FatalError
from fruitfly_agent.providers.registry import ProviderRegistry


class ModelCallBudget:
    def __init__(self, limit, *, receipt=None):
        if type(limit) is not int or limit < 1:
            raise ValueError('model call limit must be a positive integer')
        self.limit, self.used = limit, 0
        self.receipt = Path(receipt) if receipt else None
        self.write()

    def write(self):
        if self.receipt is None:
            return
        self.receipt.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.request-budget-', dir=self.receipt.parent)
        try:
            with os.fdopen(fd, 'w') as out:
                json.dump({'schema_version': 1, 'limit': self.limit, 'used': self.used}, out)
            os.replace(name, self.receipt)
        finally:
            Path(name).unlink(missing_ok=True)

    def reserve(self):
        if self.used >= self.limit:
            raise FatalError('model request allowance exhausted', details={'kind': 'model_budget_exhausted', 'limit': self.limit})
        self.used += 1
        # Persist before invoking the Provider; uncertain responses remain charged.
        self.write()


class BudgetedProvider:
    def __init__(self, provider, budget):
        self.provider, self.budget = provider, budget
        self.transport_parameters = getattr(provider, 'transport_parameters', None)

    def __call__(self, view, *, signal=None):
        self.budget.reserve()
        return self.provider(view, signal=signal)

    async def aclose(self):
        close = getattr(self.provider, 'aclose', None)
        if close is not None:
            await close()


class BudgetedProviderRegistry(ProviderRegistry):
    def __init__(self, registry, budget):
        super().__init__()
        self.registry, self.budget = registry, budget

    def register(self, name, factory):
        self.registry.register(name, factory)

    def create(self, spec, env=None):
        return BudgetedProvider(self.registry.create(spec, env), self.budget)
