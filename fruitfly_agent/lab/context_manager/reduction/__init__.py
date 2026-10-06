"""Single Provider-backed reduction algorithm."""

from .config import SummarizingCompactorConfig
from .summarizing import SummarizingCompactor, install as install_summarizing

__all__ = ["SummarizingCompactor", "SummarizingCompactorConfig", "install_summarizing"]
