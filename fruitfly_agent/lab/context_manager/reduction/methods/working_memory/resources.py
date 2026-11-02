"""Mount one working-memory history on the current run's read capability."""
from ....resources.mount import mount_history


def install_history(context):
    return mount_history(context)
