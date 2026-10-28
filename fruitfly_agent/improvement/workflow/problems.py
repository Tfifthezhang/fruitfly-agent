"""Explicit search operations; single tasks and task sets share one round engine."""
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class SearchProblem:
    begin: Callable
    propose: Callable
    probe: Callable
    compose: Callable
    select: Callable
    stop: Callable
    advance: Callable
    record: Callable

    state: Any = None
    services: Any = None
    managed: bool = False
