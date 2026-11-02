"""Working-memory reduction through the Core context contract."""
from .methods.working_memory.config import WorkingMemoryConfig
from .methods.working_memory.algorithm import WorkingMemoryReducer
from .methods.layered_compaction import LayeredCompactionReducer, LayeredCompactionConfig

__all__ = ["WorkingMemoryConfig", "WorkingMemoryReducer", "LayeredCompactionReducer", "LayeredCompactionConfig"]
