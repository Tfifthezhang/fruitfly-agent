"""Supported Run entry point; implementation belongs to its owning module."""
from .runtime.assembly import RuntimeAssembly, build_runtime
from .runtime.manifest import RuntimeManifest
from .storage.prompts import resolve_base_prompt
