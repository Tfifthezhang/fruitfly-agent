"""Skill discovery and catalog rendering."""

from fruitfly_agent.lab.context_manager.augmentation.skills.methods.indexed_documents.parser import LoadResult, Skill, load_skills, render_skills_xml
from fruitfly_agent.lab.context_manager.augmentation.skills.methods.indexed_documents.algorithm import SkillCatalogTransformer

__all__ = [
    "Skill",
    "LoadResult",
    "load_skills",
    "render_skills_xml",
    "SkillCatalogTransformer",
]
