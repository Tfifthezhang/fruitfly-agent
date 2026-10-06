"""Pluggable runtime capabilities built on the stable Core contracts."""

from .context_manager.augmentation.information import (
    InformationHub,
    InformationQuery,
    create_file_memory_space,
    create_live_http_space,
    create_local_knowledge_space,
)
from .context_manager.augmentation.skills import Skill, load_skills, render_skills_xml
from .context_manager.reduction import SummarizingCompactor, SummarizingCompactorConfig
from .environment import LocalEnv
from .tools import builtin_tools

__all__ = [
    "InformationHub",
    "InformationQuery",
    "create_file_memory_space",
    "create_local_knowledge_space",
    "create_live_http_space",
    "Skill",
    "load_skills",
    "render_skills_xml",
    "SummarizingCompactor",
    "SummarizingCompactorConfig",
    "LocalEnv",
    "builtin_tools",
]
