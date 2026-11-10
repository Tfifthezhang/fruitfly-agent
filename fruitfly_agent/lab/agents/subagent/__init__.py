"""Public managed child execution and embedding contracts."""
from .contracts import ChildRequest, ExecutionIdentity, ChildExecutionFactory
from .service import SubagentService, SubagentError

__all__ = ['ChildRequest', 'ExecutionIdentity', 'ChildExecutionFactory', 'SubagentService', 'SubagentError']
