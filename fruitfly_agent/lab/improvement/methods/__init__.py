"""Method declarations independent of a target's H/S/I classification."""
from dataclasses import dataclass
from typing import Callable, Any


@dataclass(frozen=True)
class MethodUsage:
    trigger: str
    materials: str
    feedback: str
    candidates: str
    comparison: str
    activation: str

    @property
    def details(self):
        return (('Trigger', self.trigger), ('Required materials', self.materials),
            ('Feedback', self.feedback), ('Candidate generator', self.candidates),
            ('Acceptance', self.comparison), ('Activation', self.activation))


@dataclass(frozen=True)
class MethodDefinition:
    """Declare legal bindings; construction must not execute a search."""
    roles: frozenset[str]
    schemas: frozenset[str]
    required_capabilities: frozenset[str]
    bind: Callable[[Any], Any]
    usage: MethodUsage | None = None
    prepare_targets: Callable[[Any, Any], Any] | None = None

    def __post_init__(self):
        if self.prepare_targets is not None and not callable(self.prepare_targets):
            raise TypeError('method target preparation must be callable')
        if self.usage is not None and not isinstance(self.usage, MethodUsage):
            raise TypeError('method usage must be a MethodUsage')
        for name in ('roles', 'schemas', 'required_capabilities'):
            values = getattr(self, name)
            if isinstance(values, str):
                raise ValueError('method support must contain sets of identifiers')
            object.__setattr__(self, name, frozenset(values))
        if not self.roles or not self.roles <= {'H', 'S', 'I'}:
            raise ValueError('method needs explicit supported H/S/I roles')
        if not self.schemas or any(not isinstance(s, str) or not s.strip() for s in self.schemas):
            raise ValueError('method needs explicit target schemas')
        if any(not isinstance(s, str) or not s.strip() for s in self.required_capabilities):
            raise ValueError('method needs named capabilities')
        if not callable(self.bind):
            raise TypeError('method binder must be callable')
