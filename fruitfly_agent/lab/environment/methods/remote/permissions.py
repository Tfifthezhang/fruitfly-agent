"""Remote path authorization without consulting the host filesystem."""
from pathlib import Path

from fruitfly_agent.core.errors import Result
from fruitfly_agent.lab.environment.guarded import GuardedEnv
from fruitfly_agent.lab.environment.permissions import PermissionAuthorizer
from fruitfly_agent.lab.tools.path_utils import normalize_tool_path


class RemoteAuthorizer(PermissionAuthorizer):
    def __init__(self, backend, policy, *, confirm=None, audit=None):
        super().__init__(policy, confirm=confirm, audit=audit)
        self.backend = backend
        self.execution_label = f'remote code execution on {backend.config.host}:{backend.config.port}'
        self.execution_denial = 'remote execution requires user confirmation'

    @property
    def workspace(self):
        return Path(self.backend.cwd)

    def resolve(self, path):
        result = self.backend.canonical_path(normalize_tool_path(path))
        if not result.is_ok:
            raise PermissionError('remote path could not be verified')
        return Path(result.unwrap())

    def identity(self):
        return {'implementation': 'ssh-permissions-v1', 'workspace': self.backend.cwd,
                'host': self.backend.config.host, 'port': self.backend.config.port,
                'outside_workspace': 'confirm', 'remote_execution': 'confirm',
                'secret_names': ['.env', '.env.* (except examples)', 'secrets.env', '.ssh'],
                'environment': 'remote-minimal-v1',
                'network_reads': 'allow' if self.policy.allow_network else 'deny'}

    def file_roots(self, operation):
        # Host extra roots and Session paths describe another filesystem. They
        # never confer privileges on same-spelled paths on the server.
        return (self.resolve(self.backend.cwd),)

    def forbidden(self, path, operation):
        return self.secret_name(path) or any(part == '.ssh' for part in path.parts)

    def session_target(self, path):
        info = self.backend.file_info(str(path))
        return path if info.is_ok and info.unwrap().kind == 'directory' else path.parent


class GuardedSshEnv(GuardedEnv):
    def __init__(self, backend, authorizer):
        super().__init__(backend, authorizer)
        self.cwd = backend.cwd

    def _temp(self, prefix, suffix=None):
        try:
            self.authorizer.check(self.cwd + '/.fruitfly/tmp', 'write')
            result = (self.backend.create_temp_dir(prefix) if suffix is None
                      else self.backend.create_temp_file(prefix, suffix))
            if result.is_ok:
                self.authorizer.check(result.unwrap(), 'write')
            return result
        except (OSError, ValueError, PermissionError):
            return Result.failure('Permission denied: remote temporary path could not be verified')
