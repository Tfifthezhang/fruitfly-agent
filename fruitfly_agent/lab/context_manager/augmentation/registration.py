"""Compose context augmentation owners without hosting their algorithms."""
from .information.registration import definitions as information
from .memory.improvement import definitions as memory
from .skills.registration import definitions as skills


def definitions():
    return (*information(), *memory(), *skills())
