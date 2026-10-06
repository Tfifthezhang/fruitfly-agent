"""Research execution environments, organized as one module per implementation.

An implementation that outgrows one readable module should become a same-named
subpackage; its internal filesystem/shell split remains private to that env.
"""

from .local import LocalEnv

__all__ = ["LocalEnv"]
