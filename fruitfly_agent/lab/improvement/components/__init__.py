"""Public component ownership and projection adapters."""
from .registry import ComponentRegistry
from .text import TextComponentAdapter, component_registry, bundle_target, bundle_text
from .files import FileComponentAdapter

__all__ = ["ComponentRegistry", "TextComponentAdapter", "FileComponentAdapter", "component_registry", "bundle_target", "bundle_text"]
