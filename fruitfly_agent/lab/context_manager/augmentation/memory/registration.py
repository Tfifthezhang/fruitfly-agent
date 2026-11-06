"""Register replaceable memory implementations through the existing Catalog."""
from .methods.file_memory.registration import definition


def definitions():
    return (definition(),)
