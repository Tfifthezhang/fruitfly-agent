"""Native CLI arguments preserve complete system configuration across host engines."""
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class NativeInvocation:
    python: str
    profile: str
    instruction: str
    config: str = '/installed-agent/fruitfly/runtime/config.yaml'
    session: str = '/logs/agent/session.jsonl'
    cwd: str = '.'

    def __post_init__(self):
        for label in ('python', 'config', 'session'):
            value = getattr(self, label)
            if (not isinstance(value, str) or not value or '\x00' in value
                    or not PurePosixPath(value).is_absolute() or '..' in PurePosixPath(value).parts):
                raise ValueError('native invocation requires an absolute container ' + label)
        for label in ('profile', 'cwd'):
            value = getattr(self, label)
            if not isinstance(value, str) or not value.strip() or '\x00' in value:
                raise ValueError('native invocation requires ' + label)
        if not isinstance(self.instruction, str) or '\x00' in self.instruction:
            raise ValueError('native instruction must be text without NUL')

    def argv(self) -> list[str]:
        """Return an argument vector; the host owns quoting, process lifetime and logs."""
        return [self.python, '-P', '-m', 'fruitfly_agent', '--unrestricted',
                '--cwd', self.cwd, '--config', self.config, '--profile', self.profile,
                '--session', self.session, '--', self.instruction]
