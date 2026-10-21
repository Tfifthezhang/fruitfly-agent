"""Host policy construction and minimal child-process environments."""
from pathlib import Path
from fruitfly_agent.lab.catalog import PermissionPolicy

def execution_environment(environment):
    return PermissionPolicy.prepare_environment(environment)

def default_permission_policy(workspace, config_path):
    root = Path(workspace).resolve()
    return PermissionPolicy(root, sensitive_paths=(root / '.env', root / '.fruitfly' / 'secrets.env'))
