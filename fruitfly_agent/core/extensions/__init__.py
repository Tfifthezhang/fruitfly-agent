"""Core extension seams.

The stable convenience surface remains ``fruitfly_agent.core``. Internal and
advanced callers import the precise ``hooks`` or ``protocols`` leaf module so
package initialization cannot introduce a config cycle.
"""

__all__: list[str] = []
