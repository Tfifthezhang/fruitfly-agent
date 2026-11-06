"""Public owner entry for memory execution, content and isolated learning trials."""
from .registration import definitions


def execution_definitions():
    from .methods.file_memory.trials import definition
    return (definition(),)


__all__ = ['definitions', 'execution_definitions']
