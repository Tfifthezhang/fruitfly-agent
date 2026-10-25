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

    def settle(self, kind, amount):
        """Charge previously held external work even after deadline/cancellation.

        This cannot allocate new work. Unknown outcomes consume their held maximum;
        callers record observed usage separately from conservative quota charges.
        """
        if self.closed or self.parent is None or kind not in self.limits or type(amount) is not int or amount < 0:
            raise ValueError('invalid external budget settlement')
        if amount > self.limits[kind] - self.used[kind] - self.held[kind]:
            raise ValueError('settlement exceeds held external allocation')
        parent = self.parent
        while parent is not None:
            if parent.held[kind] < amount:
                raise ValueError('external allocation is no longer held')
            parent.held[kind] -= amount
            parent.used[kind] += amount
            parent = parent.parent
        self.used[kind] += amount

    def snapshot(self):
        if self.parent is not None or any(self.held.values()):
            raise ValueError('snapshot requires an unheld root allocation')
        return {'limits': dict(self.limits), 'used': dict(self.used),
            'deadline_utc': time.time() + self.deadline - time.monotonic() if self.deadline is not None else None}

    def restore(self, snapshot):
        if self.parent is not None or self.closed or any(self.held.values()) or snapshot.get('limits') != self.limits:
            raise ValueError('persisted root allocation differs or is already active')
        used = snapshot.get('used')
        if not isinstance(used, dict) or set(used) != set(self.limits) or any(
                type(used[k]) is not int or not 0 <= used[k] <= self.limits[k] for k in self.limits):
            raise ValueError('invalid persisted allocation usage')
        for kind in self.limits:
            self.used[kind] = max(self.used[kind], used[kind])
        deadline = snapshot.get('deadline_utc')
        if deadline is not None:
            if isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or not math.isfinite(deadline):
                raise ValueError('invalid persisted allocation deadline')
            self.deadline = min(self.deadline or float('inf'), time.monotonic() + deadline - time.time())

    def forfeit(self):
        """Conservatively consume uncertain external work after process loss."""
        if self.parent is not None or any(self.held.values()):
            raise ValueError('forfeit requires an unheld root allocation')
        self.used.update(self.limits)

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
