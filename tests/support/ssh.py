"""Offline SFTP mapping and local subprocess-backed SSH command channels."""
import os
import shlex
import subprocess
import sys
from types import SimpleNamespace


class SftpFixture:
    """Map server paths into an isolated directory; no network socket."""
    def __init__(self, root):
        self.root = root
        self.closed = False

    def path(self, path):
        return self.root / path.lstrip('/')

    def stat(self, path):
        return SimpleNamespace(**self.attrs(self.path(path).stat()))

    def lstat(self, path):
        return SimpleNamespace(**self.attrs(self.path(path).lstat()))

    @staticmethod
    def attrs(value):
        return {name: getattr(value, name) for name in ('st_mode', 'st_size', 'st_mtime')}

    def readlink(self, path):
        return os.readlink(self.path(path))

    def listdir_attr(self, path):
        return [SimpleNamespace(filename=item.name, **self.attrs(item.lstat())) for item in self.path(path).iterdir()]

    def open(self, path, mode):
        return self.path(path).open(mode.replace('wx', 'xb'))

    def mkdir(self, path, mode=0o777):
        self.path(path).mkdir(mode=mode)

    def chmod(self, path, mode):
        self.path(path).chmod(mode)

    def posix_rename(self, source, destination):
        self.path(source).replace(self.path(destination))

    def remove(self, path):
        self.path(path).unlink()

    def rmdir(self, path):
        self.path(path).rmdir()

    def close(self):
        self.closed = True


class ProcessChannel:
    """Exercise the actual transmitted supervisor as a local subprocess."""
    def __init__(self):
        self.buffers = [bytearray(), bytearray()]
        self.process = None
        self.closed = False

    def exec_command(self, command):
        args = shlex.split(command)
        self.process = subprocess.Popen([sys.executable, *args[1:]], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for pipe in (self.process.stdout, self.process.stderr):
            os.set_blocking(pipe.fileno(), False)

    def settimeout(self, value):
        pass

    def ready(self, index):
        pipe = (self.process.stdout, self.process.stderr)[index]
        try:
            self.buffers[index].extend(os.read(pipe.fileno(), 65536))
        except BlockingIOError:
            pass
        return bool(self.buffers[index])

    def recv_ready(self):
        return self.ready(0)

    def recv_stderr_ready(self):
        return self.ready(1)

    def receive(self, index, size):
        data = bytes(self.buffers[index][:size])
        del self.buffers[index][:size]
        return data

    def recv(self, size):
        return self.receive(0, size)

    def recv_stderr(self, size):
        return self.receive(1, size)

    def exit_status_ready(self):
        return self.process.poll() is not None

    def recv_exit_status(self):
        return self.process.wait()

    def sendall(self, data):
        self.process.stdin.write(data)
        self.process.stdin.flush()

    def shutdown_write(self):
        self.process.stdin.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process is not None:
            if not self.process.stdin.closed:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process.stdout.close()
            self.process.stderr.close()


