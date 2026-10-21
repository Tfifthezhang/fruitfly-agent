"""Public host assembly for file policy and local execution authorization."""
from fruitfly_agent.lab.environment.permissions import PermissionPolicy
from fruitfly_agent.lab.environment.execution import UnrestrictedExecutionPolicy

def apply_permission_policy(config, policy, *, confirm, audit=None, process_environment=None):
    return policy.bind(config, confirm=confirm, audit=audit, process_environment=process_environment)

__all__ = ['PermissionPolicy', 'UnrestrictedExecutionPolicy', 'apply_permission_policy']
