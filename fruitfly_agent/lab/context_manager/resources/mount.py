"""Assemble a session-scoped public history without owning an algorithm."""
from .history import SessionHistory
from .views import history_view


def mount_history(context, *, namespace='memory', artifact_subdir='reduction'):
    from pathlib import PurePosixPath
    if (not namespace or '/' in namespace or '..' in PurePosixPath(artifact_subdir).parts
            or PurePosixPath(artifact_subdir).is_absolute()):
        raise ValueError('history requires a scoped relative namespace and artifact directory')
    root = (context.session_path.with_suffix(context.session_path.suffix + '.artifacts') / artifact_subdir
            if context.session_path is not None else None)
    history = SessionHistory(root, session=context.session)
    if context.resources is not None:
        history.resource_prefix = context.resources.mount(namespace, lambda path: history_view(history, path))
    return history
