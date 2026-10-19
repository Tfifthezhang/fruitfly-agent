"""Public host assembly for file policy and local execution authorization."""
from dataclasses import replace
from fruitfly_agent.lab.environment.permissions import PermissionPolicy, PermissionAuthorizer
from fruitfly_agent.lab.environment.guarded import GuardedEnv

def apply_permission_policy(config, policy, *, confirm, audit=None, process_environment=None):
    authorizer = PermissionAuthorizer(policy, confirm=confirm, audit=audit)
    env = config.env
    adapter = getattr(env, 'with_permissions', None)
    if adapter is not None:
        env, authorizer = adapter(policy, confirm=confirm, audit=audit)
        return replace(config, env=env, tool_authorizer=authorizer)
    if env is not None:
        env = GuardedEnv(env, authorizer, process_environment=process_environment)
    return replace(config, env=env, tool_authorizer=authorizer)

__all__ = ['PermissionPolicy', 'apply_permission_policy']
