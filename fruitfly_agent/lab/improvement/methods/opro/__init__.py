"""Public entry point for the native OPRO improvement method."""

from fruitfly_agent.lab.improvement.methods.opro.improver import OproImprover
from fruitfly_agent.lab.improvement.methods.opro.registration import definition

__all__ = ["OproImprover", "definition"]
