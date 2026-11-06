"""Compose explicit owner declarations; construction stays with each owner."""
from .catalog import LabCatalog
from .defaults import declared_defaults
from fruitfly_agent.lab.environment.improvement import definitions as environments
from fruitfly_agent.lab.tools.registration import definitions as tools
from fruitfly_agent.lab.mcp.improvement import definitions as mcp
from fruitfly_agent.lab.base_prompt.registration import definition as instructions
from fruitfly_agent.lab.context_manager.augmentation.registration import definitions as augmentation
from fruitfly_agent.lab.context_manager.reduction.registration import definitions as reduction
from fruitfly_agent.lab.context_manager.externalization.improvement import definitions as externalization
from fruitfly_agent.lab.context_manager.measurement.registration import install as measurement
from fruitfly_agent.lab.improvement.registration import definition as improvement


def builtin_catalog():
    return LabCatalog(tuple(declared_defaults(d) for d in (
        instructions(), *environments(), *tools(), *mcp(), *augmentation(),
        *reduction(), *externalization(), improvement(),
    )), bootstrap=measurement)
