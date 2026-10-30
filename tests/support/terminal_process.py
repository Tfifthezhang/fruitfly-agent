"""A bounded POSIX terminal process for offline lifecycle tests."""
import errno
import fcntl
import os
import pty
import re
import select
import signal
import sys
import struct
import termios
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TerminalProcess:
    def __init__(self, code, *, term='xterm-256color', rows=30, columns=160, environment=None):
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.chdir(ROOT)
            os.environ['TERM'] = term
            os.environ['INPUTRC'] = os.devnull
            for key, value in (environment or {}).items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            os.execl(sys.executable, sys.executable, '-c', code)
        self.output = b''
        self.status = None
        self._closed = False
        self._eof = False
        self.resize(rows, columns)

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.close()

    def send(self, data):
        os.write(self.fd, data)

    def signal(self):
        os.kill(self.pid, signal.SIGINT)

    def resize(self, rows, columns):
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack('HHHH', rows, columns, 0, 0))

    def read_until(self, marker, *, timeout=5, start=0):
        marker = marker.encode() if isinstance(marker, str) else marker
        deadline = time.monotonic() + timeout
        while marker not in re.sub(rb'\x1b\[[0-9;]*m', b'', self.output[start:]):
            if self._eof or time.monotonic() >= deadline:
                raise AssertionError(f'terminal did not report {marker!r}: {self.output[-2000:]!r}')
            self._read()
        return self.output.decode(errors='replace')

    def _read(self):
        if select.select([self.fd], [], [], 0.05)[0]:
            try:
                chunk = os.read(self.fd, 8192)
                self.output += chunk
                self._eof = not chunk
            except OSError as exc:
                if exc.errno != errno.EIO:
                    raise
                self._eof = True

    def finish(self, *, timeout=5):
        deadline = time.monotonic() + timeout
        while self.status is None:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid:
                self.status = status
                break
            if time.monotonic() >= deadline:
                raise AssertionError(f'terminal did not exit: {self.output[-2000:]!r}')
            self._read()
        while not self._eof and select.select([self.fd], [], [], 0.05)[0]:
            self._read()
        if os.waitstatus_to_exitcode(self.status) != 0:
            raise AssertionError(f'terminal failed: {self.output[-2000:]!r}')
        return self.output.decode(errors='replace')

    def close(self):
        if self._closed:
            return
        if self.status is None:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(self.pid, 0)
            except ChildProcessError:
                pass
        os.close(self.fd)
        self._closed = True


def run_terminal(code, keys, *, prompt='❯ ', **options):
    """Submit only after a visible prompt and always retire the child process."""
    with TerminalProcess(code, **options) as terminal:
        terminal.read_until(prompt)
        terminal.send(keys)
        return terminal.finish()
