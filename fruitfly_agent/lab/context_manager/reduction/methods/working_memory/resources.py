"""Mount one working-memory history on the current run's read capability."""
from ....resources import SessionHistory
from ....resources.views import history_view


def install_history(context):
    root = (context.session_path.with_suffix(context.session_path.suffix + '.artifacts') / 'reduction'
            if context.session_path is not None else None)
    history = SessionHistory(root, session=context.session)
    if context.resources is not None:
        history.resource_prefix = context.resources.mount('memory', lambda path: history_view(history, path))
    else:
        history.resource_prefix = ''
    return history
