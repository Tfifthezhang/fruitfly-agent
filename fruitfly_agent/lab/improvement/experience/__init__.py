"""Validate pending lessons independently of storage and activation."""
from dataclasses import asdict

from ..contracts.pipeline import ExperienceEntry, HarnessSnapshot, experience_id


def entry_to_dict(entry):
    return asdict(entry)


def entry_from_dict(value):
    if not isinstance(value, dict) or set(value) != set(ExperienceEntry.__dataclass_fields__):
        raise ValueError('invalid experience entry')
    return ExperienceEntry(**{**value, 'harness': HarnessSnapshot.from_dict(value['harness']),
                              'evidence_ids': tuple(value['evidence_ids'])})


__all__ = ['entry_to_dict', 'entry_from_dict', 'experience_id']
