"""Keep WorkBuddy's official Docker behavior with shared preparation and ownership."""
from pathlib import Path, PurePosixPath
import shlex
from workbuddy_bench.runner.docker_environment import WorkBuddyDockerEnvironment  # type: ignore[import-not-found, import-untyped, unused-ignore]
from fruitfly_eval.backends.mounts import PreparedMounts


class PreparedWorkBuddyEnvironment(PreparedMounts, WorkBuddyDockerEnvironment):
    async def upload_file(self, source_path: Path | str, target_path: str) -> None:
        target = PurePosixPath(target_path)
        if not target.is_absolute() or '..' in target.parts:
            raise ValueError('upload target must be an absolute container path without traversal')
        await super().upload_file(source_path, target_path)
        # The official judge rewrites /tests/verifier.py through a mode-600
        # temporary file, and docker cp preserves that mode, so the official
        # non-root verifier user cannot read its own script. Normalize only
        # the container copy of official test files to the frozen 644 mode;
        # host and frozen files are never touched, and scoring is unchanged.
        if str(target) != '/tests' and target.is_relative_to('/tests'):
            result = await self.exec(command='chmod 644 ' + shlex.quote(str(target)),
                                     user='root', timeout_sec=30)
            if result.return_code:
                raise RuntimeError('cannot normalize uploaded test file permissions: ' + str(target))
