"""A bounded POSIX terminal process for offline lifecycle tests."""
import errno
import fcntl
import os
import pty
import select
import signal
import sys
import struct
import termios
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TerminalProcess:
    def __init__(self, code, *, term='xterm-256color'):
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.chdir(ROOT)
            os.environ['TERM'] = term
            os.environ['INPUTRC'] = os.devnull
            os.execl(sys.executable, sys.executable, '-c', code)
        self.output = b''
        self.status = None
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 160, 0, 0))

    def send(self, data):
        os.write(self.fd, data)

    def signal(self):
        os.kill(self.pid, signal.SIGINT)

    def read_until(self, marker, *, timeout=5):
        marker = marker.encode() if isinstance(marker, str) else marker
        deadline = time.monotonic() + timeout
        while marker not in self.output:
            if time.monotonic() >= deadline:
                raise AssertionError(f'terminal did not report {marker!r}: {self.output[-2000:]!r}')
            self._read()
        return self.output.decode(errors='replace')

    def _read(self):
        if select.select([self.fd], [], [], 0.05)[0]:
            try:
                chunk = os.read(self.fd, 8192)
                self.output += chunk
            except OSError as exc:
                if exc.errno != errno.EIO:
                    raise

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
        self._read()
        if os.waitstatus_to_exitcode(self.status) != 0:
            raise AssertionError(f'terminal failed: {self.output[-2000:]!r}')
        return self.output.decode(errors='replace')

    def close(self):
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
