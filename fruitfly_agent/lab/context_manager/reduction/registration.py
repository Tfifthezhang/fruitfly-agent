"""Explicit reduction composition; hosts never branch on concrete methods."""


def definitions():
    from .methods.working_memory.registration import definition as working_memory
    from .methods.layered_compaction.registration import definition as layered_compaction
    return (layered_compaction(), working_memory())
