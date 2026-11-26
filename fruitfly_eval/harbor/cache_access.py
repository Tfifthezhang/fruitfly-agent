"""Grant an effective container group access to owned dependency caches."""
import os
from pathlib import Path
import stat
import sys

ROOT = Path('/opt/fruitfly-eval-dependencies/cache')


def grant(gid: int) -> None:
    if gid < 0:
        raise ValueError('invalid cache group')
    paths = [ROOT, *(ROOT / name for name in ('uv', 'python', 'pip'))]
    for path in paths:
        if path != ROOT and not path.exists() and not path.is_symlink():
            path.mkdir(mode=0o700)
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or info.st_gid not in {os.getgid(), gid}:
                raise ValueError('cache root has incompatible ownership; use a dedicated prepared cache')
            os.fchown(fd, -1, gid)
            os.fchmod(fd, 0o2770)
        finally:
            os.close(fd)


async def configure(environment, python, runtime_environment, *, user=None):
    import shlex
    identity = await environment.exec(command='id -g', user=user, timeout_sec=10)
    if identity.return_code:
        raise RuntimeError('cannot resolve dependency cache execution group')
    gid = int(identity.stdout.strip())
    result = await environment.exec(command=shlex.join([python, '-P', '-m',
        'fruitfly_eval.harbor.cache_access', str(gid)]), user='root',
        env=runtime_environment, timeout_sec=60)
    if result.return_code:
        raise RuntimeError('cannot grant scoped dependency cache access')


if __name__ == '__main__':
    grant(int(sys.argv[1]))
