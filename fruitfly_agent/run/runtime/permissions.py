"""Host policy construction and minimal child-process environments."""
from pathlib import Path
from fruitfly_agent.lab.catalog import PermissionPolicy

def execution_environment(environment):
    return PermissionPolicy.prepare_environment(environment)

def default_permission_policy(workspace, config_path, *, user_root=None):
    from fruitfly_agent.providers.auth.stores import auth_directory
    root = Path(workspace).resolve()
    personal = Path(user_root) if user_root is not None else root / '.fruitfly'
    return PermissionPolicy(root, sensitive_paths=(root / '.env', root / '.fruitfly' / 'secrets.env', auth_directory(), personal))
