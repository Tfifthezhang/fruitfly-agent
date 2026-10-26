"""Offline, strict stdio server configuration. Secrets are named separately."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import math
import re
import yaml

_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$')
_ENV = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


class _UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, (str, int, float, bool, type(None))) or key in result:
                raise yaml.YAMLError('duplicate or invalid mapping key')
            result[key] = self.construct_object(value_node, deep=deep)
        return result


@dataclass(frozen=True)
class ServerConfig:
    name: str
    command: str
    args: tuple[str, ...]
    cwd: str
    tools: tuple[str, ...]
    env: dict[str, str] = field(default_factory=dict)
    secret_env: dict[str, str] = field(default_factory=dict)
    startup_timeout: float = 30
    call_timeout: float = 120
    close_timeout: float = 10
    max_result_bytes: int = 16 * 1024 * 1024
    inline_result_chars: int = 12000
    max_parallel: int = 1


def load_config(path: Path, workspace: Path) -> tuple[ServerConfig, ...]:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('MCP configuration exceeds 1 MiB')
    try:
        raw = yaml.load(path.read_text(encoding='utf-8'), Loader=_UniqueLoader)
    except yaml.YAMLError:
        raise ValueError('invalid MCP YAML') from None
    if not isinstance(raw, dict) or set(raw) != {'servers'} or not isinstance(raw['servers'], dict):
        raise ValueError('MCP configuration requires a servers mapping')
    servers = []
    for name, data in raw['servers'].items():
        if not isinstance(name, str) or not _ID.fullmatch(name) or not isinstance(data, dict):
            raise ValueError('MCP server requires a stable name and mapping')
        allowed = {'enabled', 'transport', 'command', 'args', 'cwd', 'tools', 'env', 'secret_env',
                   'startup_timeout', 'call_timeout', 'close_timeout', 'max_result_bytes', 'inline_result_chars', 'max_parallel'}
        if set(data) - allowed:
            raise ValueError('unknown MCP server configuration field')
        enabled = data.get('enabled', True)
        if not isinstance(enabled, bool):
            raise ValueError('MCP enabled must be boolean')
        if data.get('transport', 'stdio') != 'stdio':
            raise ValueError('only stdio MCP transport is supported')
        command, args, tools = data.get('command'), data.get('args', []), data.get('tools')
        if not isinstance(command, str) or not command.strip() or '\x00' in command:
            raise ValueError('MCP command must be a nonempty executable name or path')
        if not isinstance(args, list) or any(not isinstance(v, str) or '\x00' in v for v in args):
            raise ValueError('MCP args must be a list of strings')
        if (not isinstance(tools, list) or not tools or any(not isinstance(v, str) or not v for v in tools)
                or len(set(tools)) != len(tools)):
            raise ValueError('MCP tools must explicitly select distinct tool names')
        directory = data.get('cwd', '.')
        if not isinstance(directory, str) or not directory or '\x00' in directory:
            raise ValueError('MCP cwd must be a local directory path')
        cwd = Path(directory).expanduser()
        cwd = (workspace / cwd).resolve() if not cwd.is_absolute() else cwd.resolve()
        maps: dict[str, dict[str, str]] = {}
        for key in ('env', 'secret_env'):
            values = data.get(key, {})
            if not isinstance(values, dict) or any(not isinstance(k, str) or not _ENV.fullmatch(k)
                    or not isinstance(v, str) or '\x00' in v
                    or key == 'secret_env' and not _ENV.fullmatch(v) for k, v in values.items()):
                raise ValueError('MCP environment maps require valid names and string values; secret_env values are variable names')
            maps[key] = dict(values)
        if set(maps['env']) & set(maps['secret_env']):
            raise ValueError('MCP env and secret_env must not overlap')
        options: dict[str, Any] = {}
        for key, default in (('startup_timeout', 30), ('call_timeout', 120), ('close_timeout', 10),
                             ('max_result_bytes', 16 * 1024 * 1024), ('inline_result_chars', 12000), ('max_parallel', 1)):
            value = data.get(key, default)
            integer = key in {'max_result_bytes', 'inline_result_chars', 'max_parallel'}
            if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                    or value <= 0 or integer and not isinstance(value, int)):
                raise ValueError('MCP budgets must be finite positive numbers; size and concurrency budgets are integers')
            options[key] = value
        if enabled:
            servers.append(ServerConfig(name, command, tuple(args), str(cwd), tuple(tools),
                env=maps['env'], secret_env=maps['secret_env'], **options))
    return tuple(servers)
