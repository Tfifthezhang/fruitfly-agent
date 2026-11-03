"""Environment-owned structural classification without transport messages."""
from contextlib import contextmanager
import errno
import socket
import ssl

from fruitfly_agent.core.observation import FailureInfo, operation


def classify_environment_failure(exc, stage):
    code = {'AuthenticationException': 'authentication', 'BadAuthenticationType': 'authentication',
        'BadHostKeyException': 'host_key', 'NoValidConnectionsError': 'connection',
        'ChannelException': 'channel_open', 'SSHException': 'ssh_protocol'}.get(type(exc).__name__, 'unknown')
    if isinstance(exc, socket.gaierror):
        code = 'dns'
    elif isinstance(exc, ssl.SSLError):
        code = 'tls'
    elif isinstance(exc, TimeoutError):
        code = 'timeout'
    elif isinstance(exc, PermissionError):
        code = 'permission'
    elif isinstance(exc, FileNotFoundError):
        code = 'not_found'
    elif isinstance(exc, ConnectionResetError):
        code = 'connection_reset'
    elif isinstance(exc, ConnectionRefusedError):
        code = 'connection_refused'
    number = getattr(exc, 'errno', None)
    code = {errno.ENETUNREACH: 'network_unreachable', errno.EHOSTUNREACH: 'host_unreachable',
        errno.ECONNRESET: 'connection_reset', errno.ECONNREFUSED: 'connection_refused'}.get(number, code)
    return FailureInfo('environment', stage, code, 'exception_type', exception_type=type(exc).__name__)


@contextmanager
def environment_operation(stage):
    with operation(stage, origin='environment') as observed:
        try:
            yield observed
        except Exception as exc:
            observed.fail(classify_environment_failure(exc, stage))
            raise
