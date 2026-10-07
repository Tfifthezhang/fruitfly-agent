"""Invoke run-local callbacks with call-site defaults on ordinary failure."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def call_extension(fn: Any, *args: Any, label: str, default: Any) -> Any:
    """Use the call site's default on ordinary failure; propagate cancellation."""
    try:
        result = fn(*args)
        if hasattr(result, "__await__"):
            result = await result
        return result
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s failed (isolated): %s", label, exc)
        return default
