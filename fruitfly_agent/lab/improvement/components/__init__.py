"""Public component ownership and projection adapters."""
from fruitfly_agent.improvement.components.registry import ComponentRegistry
from .text import TextComponentAdapter, component_registry, bundle_target, bundle_text
from .files import FileComponentAdapter

__all__ = ["ComponentRegistry", "TextComponentAdapter", "FileComponentAdapter", "component_registry", "bundle_target", "bundle_text"]
