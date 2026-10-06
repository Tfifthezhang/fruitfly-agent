"""Per-canonical-path mutation queue for concurrent file tools.

The loop executes tools in parallel by default; two tools writing the same
file must serialize. Keyed on the canonical path (symlinks resolved) so
aliases of one file share a queue.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

from fruitfly_agent.core.env import ExecutionEnv

T = TypeVar("T")

_locks: dict[str, asyncio.Lock] = {}


def _key_for(env: ExecutionEnv, path: str) -> str:
    canonical = env.canonical_path(path)
    if canonical.is_ok:
        return canonical.unwrap()
    return path


async def with_file_mutation_queue(
    env: ExecutionEnv, path: str, fn: Callable[[], Awaitable[T] | T]
) -> T:
    key = _key_for(env, path)
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        result = fn()
        if isinstance(result, Awaitable):
            return await result
        return result
