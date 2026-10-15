"""Shared invocation limits for a runtime hosted in an isolated trial."""
from dataclasses import replace
from inspect import isawaitable

from fruitfly_agent.core.errors import FatalError
from fruitfly_agent.providers.registry import ProviderRegistry


class TrialInvocationBudget:
    def __init__(self, max_calls: int, max_output_tokens: int):
        if any(type(v) is not int or v < 1 for v in (max_calls, max_output_tokens)):
            raise ValueError("trial invocation limits must be positive integers")
        self.max_calls, self.max_output_tokens = max_calls, max_output_tokens
        self.used = 0
        self.exhausted = False

    def reserve(self):
        if self.used >= self.max_calls:
            self.exhausted = True
            raise FatalError("isolated trial model invocation budget exhausted")
        self.used += 1


class BudgetedProvider:
    def __init__(self, provider, budget):
        self.provider, self.budget = provider, budget

    @property
    def transport_parameters(self):
        return getattr(self.provider, "transport_parameters", None)

    def __call__(self, view, *, signal=None):
        self.budget.reserve()
        return self.provider(replace(view, max_tokens=min(view.max_tokens, self.budget.max_output_tokens)), signal=signal)

    async def close(self):
        close = getattr(self.provider, "close", None)
        if close is not None:
            result = close()
            if isawaitable(result):
                await result


class BudgetedRegistry(ProviderRegistry):
    """All main and auxiliary Providers debit the same trial allocation."""
    def __init__(self, registry, budget):
        super().__init__()
        self.registry, self.budget = registry, budget
        self.wrappers = {}

    def create(self, spec, env=None):
        spec = replace(spec, max_output_tokens=min(spec.max_output_tokens, self.budget.max_output_tokens))
        provider = self.registry.create(spec, env)
        if id(provider) not in self.wrappers:
            self.wrappers[id(provider)] = BudgetedProvider(provider, self.budget)
        return self.wrappers[id(provider)]
