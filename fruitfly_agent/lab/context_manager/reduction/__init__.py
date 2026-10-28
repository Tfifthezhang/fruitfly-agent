"""Selectable reduction methods through one Core contract."""

from .methods.summarizing.config import SummarizingCompactorConfig
from .methods.summarizing.algorithm import SummarizingCompactor, install as install_summarizing
from .methods.working_memory.config import WorkingMemoryConfig
from .methods.working_memory.algorithm import WorkingMemoryReducer

__all__ = ["SummarizingCompactor", "SummarizingCompactorConfig", "install_summarizing",
           "WorkingMemoryConfig", "WorkingMemoryReducer"]
