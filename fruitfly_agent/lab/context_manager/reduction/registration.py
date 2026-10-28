"""Explicit reduction composition; hosts never branch on concrete methods."""
from dataclasses import replace
from ..history import SessionHistory, HistoryConfig
from ..registration import parameters, validate
from functools import partial
from .improvement import expose
from ...tools.context import context_tools
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects
from fruitfly_agent.lab.catalog.models import MechanismDefinition


def install_history(state, context, parameters):
    root = (context.session_path.with_suffix(context.session_path.suffix + '.artifacts') / 'reduction'
            if context.session_path is not None else None)
    history = SessionHistory(root, session=context.session, config=HistoryConfig(**parameters))
    return replace(state, config=replace(state.config, tools=(*state.config.tools, *context_tools(history)))).with_component(
        'context-history', history)


def definitions():
    from .methods.summarizing.registration import definition as summarizing
    from .methods.working_memory.registration import definition as working_memory
    history = MechanismDefinition(MechanismDescriptor('context-history', 'Context evidence',
        'Retrieve public canonical evidence and immutable reduction artifacts within one session.',
        contributions=(MechanismContribution('capability', 'context'),), default_enabled=True, install_order=54,
        parameters=parameters(HistoryConfig),
        effects=MechanismEffects(writes_files=True, tools=('context_read', 'context_search'))),
        install_history, implementation_id='context-history-v1',
        implementation_path='fruitfly_agent/lab/context_manager/history.py',
        documentation_path='fruitfly_agent/lab/context_manager/reduction/README.md',
        validate_parameters=partial(validate, HistoryConfig))
    return expose(history, HistoryConfig), summarizing(), working_memory()
