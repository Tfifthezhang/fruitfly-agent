"""FruitFlyAgent — an interactive-first harness for agent algorithms.

The package root re-exports the stable Core API. Algorithms and runtime
components live in ``fruitfly_agent.lab``; applications use the explicit
``fruitfly_agent.interactive`` and ``fruitfly_agent.run`` layers.
"""

from .core import *  # noqa: F401,F403 — deliberate re-export
from .core import __all__

__all__ = list(__all__)
