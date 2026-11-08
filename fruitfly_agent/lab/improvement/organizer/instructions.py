"""Organizer I instructions, independent of editor and assessor implementations."""
from dataclasses import dataclass, asdict, field
from fruitfly_agent.runtime_spec.documents import parameter_default
from fruitfly_agent.improvement.contracts.validation import bounded
from ..components.instructions import InstructionTarget


@dataclass(frozen=True)
class OrganizerInstructions:
    system: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.layered', 'defaults.yaml', 'instructions.system'))
    organize: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.layered', 'defaults.yaml', 'instructions.organize'))

    def __post_init__(self):
        for value in asdict(self).values():
            bounded(value, 16000)


def instruction_target(instructions=None, *, text=None):
    return InstructionTarget('improvement-organizer', instructions or OrganizerInstructions(),
        defaults=OrganizerInstructions(), label='Improvement evidence organizer', text=text,
        descriptions={'system': 'Role boundary and faithful use of original evidence.',
            'organize': 'Readable structure, summaries, navigation and source attribution.'})
