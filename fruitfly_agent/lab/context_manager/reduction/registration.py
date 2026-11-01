"""Explicit reduction composition; hosts never branch on concrete methods."""


def definitions():
    from .methods.working_memory.registration import definition as working_memory
    return (working_memory(),)
