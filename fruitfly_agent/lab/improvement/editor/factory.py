"""Select an editor through the owning configuration surface."""
from .configuration import EditorSettings


def create_editor(config, artifacts, components, *, instructions=None, settings=None,
                  runtime_factory=None, options=None, completion_session=None):
    effective = EditorSettings.from_dict(options)
    if effective.method == 'gepa-reflection':
        from .methods.gepa_reflection.algorithm import GEPAReflectionEditor
        return GEPAReflectionEditor(config, artifacts, components, sessions=completion_session)
    from .methods.workspace.algorithm import AgentEditor
    return AgentEditor(config, artifacts, components, instructions=instructions,
                       settings=settings, runtime_factory=runtime_factory, options=effective)
