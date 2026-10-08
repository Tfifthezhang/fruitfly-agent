"""Host policy construction and minimal child-process environments."""
from pathlib import Path
from fruitfly_agent.lab.catalog import PermissionPolicy

_ENV_NAMES = ('LANG', 'LC_ALL', 'LC_CTYPE', 'TZ', 'TERM')

def execution_environment(environment):
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', **{k: environment[k] for k in _ENV_NAMES if k in environment}}

def default_permission_policy(workspace, config_path):
    root = Path(workspace).resolve()
    return PermissionPolicy(root, sensitive_paths=(root / '.env', root / '.fruitfly' / 'secrets.env'))
