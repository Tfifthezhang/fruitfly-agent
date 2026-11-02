"""Session-scoped compaction resources, independent of execution filesystem."""
from ....resources.mount import mount_history


def install_history(context):
    return mount_history(context, namespace='compaction', artifact_subdir='reduction/layered_compaction')
