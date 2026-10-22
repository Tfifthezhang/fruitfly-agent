"""Hierarchical reservations. Allocated quota is held, not reported as spent."""
from __future__ import annotations

import asyncio
import time
from contextvars import ContextVar
import math

operation_deadline = ContextVar('improvement_operation_deadline', default=None)


class AllocationExhausted(RuntimeError):
    pass


class BudgetScope:
    """One synchronous ledger shared by descendants; no await between checks/charges."""

    def __init__(self, limits, *, signal=None, deadline=None, parent=None):
        if set(limits) != {'model', 'execution'} or any(type(v) is not int or v < 0 for v in limits.values()):
            raise ValueError('budget needs nonnegative model and execution limits')
        self.limits = dict(limits)
        self.used = dict.fromkeys(limits, 0)
        self.held = dict.fromkeys(limits, 0)
        self.signal = signal if signal is not None else asyncio.Event()
        self.deadline, self.parent = deadline, parent
        if deadline is not None and (not isinstance(deadline, (int, float)) or not math.isfinite(deadline)):
            raise ValueError('deadline must be finite')
        self.closed = False
        self.children = []

    def check(self):
        if self.closed:
            raise ValueError('budget scope is closed')
        if self.signal.is_set():
            raise asyncio.CancelledError('improvement cancelled')
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise TimeoutError('experiment deadline exceeded')

    def available(self, kind):
        self.check()
        return self.limits[kind] - self.used[kind] - self.held[kind]

    def child(self, limits, *, timeout=None):
        self.check()
        if set(limits) != set(self.limits) or any(type(v) is not int or v < 0 for v in limits.values()):
            raise ValueError('invalid child allocation')
        if any(v > self.available(k) for k, v in limits.items()):
            raise AllocationExhausted('child allocation exceeds remaining budget')
        deadline = self.deadline
        inherited = operation_deadline.get()
        if inherited is not None:
            deadline = min(deadline or float('inf'), inherited)
        if timeout is not None:
            if timeout <= 0:
                raise ValueError('child timeout must be positive')
            deadline = min(deadline or float('inf'), time.monotonic() + timeout)
        child = BudgetScope(limits, signal=self.signal, deadline=deadline, parent=self)
        for kind, amount in limits.items():
            self.held[kind] += amount
        self.children.append(child)
        return child

    def _charge_child(self, kind, amount):
        self.check()
        if self.parent is not None:
            self.parent._charge_child(kind, amount)
        self.held[kind] -= amount
        self.used[kind] += amount

    def reserve(self, kind, amount=1):
        self.check()
        if kind not in self.limits or type(amount) is not int or amount < 0:
            raise ValueError('invalid allocation reservation')
        if amount > self.available(kind):
            raise AllocationExhausted(kind + ' allocation exhausted')
        if self.parent is not None:
            self.parent._charge_child(kind, amount)
        self.used[kind] += amount

    def extend(self, extra):
        """Borrow unused parent quota for a protected final phase, never raise root limits."""
        self.check()
        if self.parent is None or set(extra) != set(self.limits) or any(type(v) is not int or v < 0 for v in extra.values()):
            raise ValueError('only a child can borrow nonnegative remaining quota')
        if any(v > self.parent.available(k) for k, v in extra.items()):
            raise AllocationExhausted('parent has insufficient unallocated quota')
        for kind, amount in extra.items():
            self.parent.held[kind] += amount
            self.limits[kind] += amount

    def close(self):
        if self.closed:
            return
        for child in self.children:
            child.close()
        if self.parent is not None:
            for kind in self.limits:
                self.parent.held[kind] -= self.limits[kind] - self.used[kind]
        self.closed = True
