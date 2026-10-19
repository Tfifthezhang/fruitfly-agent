"""Non-secret SSH settings; authentication values belong to the host."""
from dataclasses import dataclass
import ipaddress
import math
import posixpath
import re


@dataclass(frozen=True)
class SshConfig:
    host: str = ''
    port: int = 22
    cwd: str = '/srv/workspace'
    username_env: str = 'FRUITFLY_SSH_USERNAME'
    password_env: str = 'FRUITFLY_SSH_PASSWORD'
    known_hosts: str = '~/.ssh/known_hosts'
    connect_timeout_seconds: float = 15
    operation_timeout_seconds: float = 30

    def __post_init__(self):
        if not isinstance(self.host, str) or any(c.isspace() or ord(c) < 32 for c in self.host) or any(c in self.host for c in '@/'):
            raise ValueError('SSH host must be a hostname or IP address without credentials or a port')
        if ':' in self.host:
            try:
                ipaddress.IPv6Address(self.host)
            except ValueError:
                raise ValueError('Set the SSH port separately from the host; IPv6 addresses use no brackets') from None
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError('SSH port must be an integer from 1 to 65535')
        if not isinstance(self.cwd, str) or not self.cwd.startswith('/') or '\x00' in self.cwd or any(ord(c) < 32 for c in self.cwd):
            raise ValueError('SSH cwd must be an absolute POSIX directory')
        object.__setattr__(self, 'cwd', posixpath.normpath(self.cwd))
        for name in ('username_env', 'password_env'):
            if not isinstance(getattr(self, name), str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', getattr(self, name)):
                raise ValueError(f'{name} must name a secret environment variable')
        if self.username_env == self.password_env:
            raise ValueError('SSH username and password require distinct secret variables')
        if not isinstance(self.known_hosts, str) or not self.known_hosts or '\x00' in self.known_hosts:
            raise ValueError('SSH known_hosts must name a local host-key file')
        for name in ('connect_timeout_seconds', 'operation_timeout_seconds'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not .1 <= value <= 300:
                raise ValueError(f'{name} must be between 0.1 and 300 seconds')
