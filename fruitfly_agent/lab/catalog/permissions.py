"""Public host assembly for file policy and local execution authorization."""
from fruitfly_agent.lab.environment.permissions import PermissionPolicy
from fruitfly_agent.lab.environment.execution import UnrestrictedExecutionPolicy

def apply_permission_policy(config, policy, *, confirm, audit=None, process_environment=None):
    from dataclasses import replace
    from fruitfly_agent.lab.tools.resources import ResourceAuthorizer
    configured = policy.bind(config, confirm=confirm, audit=audit, process_environment=process_environment)
    return replace(configured, tool_authorizer=ResourceAuthorizer(configured.readable_resources, configured.tool_authorizer))

__all__ = ['PermissionPolicy', 'UnrestrictedExecutionPolicy', 'apply_permission_policy']
