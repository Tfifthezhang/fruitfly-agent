"""Working-memory policy admission through shared component contracts."""
from ...improvement import expose
from .config import WorkingMemoryConfig


def register(definition):
    return expose(definition, WorkingMemoryConfig, protected=('memory_model_profile',))
