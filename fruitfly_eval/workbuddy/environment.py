"""Keep WorkBuddy's official Docker behavior with shared preparation and ownership."""
from workbuddy_bench.runner.docker_environment import WorkBuddyDockerEnvironment  # type: ignore[import-not-found, import-untyped, unused-ignore]
from fruitfly_eval.backends.mounts import PreparedMounts


class PreparedWorkBuddyEnvironment(PreparedMounts, WorkBuddyDockerEnvironment):
    pass
