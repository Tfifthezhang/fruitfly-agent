"""Text tree-search registration and the independently versioned policy target."""
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects, ParameterDescriptor as P
from fruitfly_agent.lab.algorithms.targets import TEXT_TARGET_PREFIX
from ...methods import MethodDefinition
from ...registration import install_text_improver, text_target_parameters, text_budget_parameters
from .improver import TreeSearchImprover
from .policy import ExplorationPolicy
from .target import PolicyTarget, POLICY_TARGET


def search_parameters():
    return (P('rounds', 'integer', 'Search rounds', 'Maximum decision rounds.', 4, minimum=1, maximum=128),
        P('workers', 'integer', 'Parallel workers', 'Maximum simultaneous discovery attempts.', 2, minimum=1, maximum=16),
        P('discovery_calls', 'integer', 'Discovery attempts', 'Maximum candidate-generation attempts per search.', 8, minimum=1, maximum=128),
        P('history_path', 'path', 'Discovery histories', 'Workspace-relative completed search history directory.', '.fruitfly/improvement/discovery'))


def definition():
    from fruitfly_agent.lab.catalog.models import MechanismDefinition
    return MechanismDefinition(MechanismDescriptor('tree-search', 'Tree search',
        'Search instruction branches and retain real scored discovery histories.',
        contributions=(MechanismContribution('improvement', 'context'), MechanismContribution('improvement', 'workflow')),
        parameters=(*text_target_parameters(), *text_budget_parameters(), *search_parameters()),
        exclusive_group='text-improver', install_order=76,
        effects=MechanismEffects(uses_provider=True, uses_network=True, writes_files=True,
            cost_notice='Explicit search calls models, evaluates tasks and stores discovery histories.')),
        _install, implementation_id=TreeSearchImprover.spec.implementation_id,
        artifact_slots=frozenset({POLICY_TARGET}), provides=frozenset({'text-improver', 'tree-search'}),
        selection_group='text-improver', selection_group_label='Text improver',
        improvement=MethodDefinition(TreeSearchImprover.supported_roles, TreeSearchImprover.supported_schemas,
            TreeSearchImprover.required_capabilities, _bind, usage=TreeSearchImprover.usage,
            prepare_targets=_prepare_targets))


def _prepare_targets(state, context):
    if (TEXT_TARGET_PREFIX + POLICY_TARGET in state.components
            or TEXT_TARGET_PREFIX + 'base_prompt' not in state.components):
        return state
    return _policy_target(state, context, 'base_prompt')


def _policy_target(state, context, execution_target_id):
    execution_target = state.components[TEXT_TARGET_PREFIX + execution_target_id]
    text = ExplorationPolicy().serialize()
    reference = context.artifact_bindings.get(POLICY_TARGET)
    if reference:
        if context.artifact_reader is None:
            raise ValueError('policy artifact requires an artifact reader')
        text = context.artifact_reader(reference)
        state = state.with_data_artifact({'key': POLICY_TARGET, 'id': reference, 'role': 'I',
            'media_type': 'application/json', 'size_bytes': len(text.encode())})
    return state.with_component(TEXT_TARGET_PREFIX + POLICY_TARGET, PolicyTarget(text, execution_target))


def _install(state, context, parameters):
    state = _policy_target(state, context, parameters['target'])
    text = state.components[TEXT_TARGET_PREFIX + POLICY_TARGET].snapshot().text
    return install_text_improver(state, context, parameters,
        strategy=TreeSearchImprover(ExplorationPolicy.parse(text), context.workspace), label='Tree search', roles=())


def _bind(binding):
    target = binding.components.get(TEXT_TARGET_PREFIX + POLICY_TARGET)
    policy = ExplorationPolicy.parse(target.snapshot().text) if target else ExplorationPolicy()
    return binding.text_host(TreeSearchImprover(policy, binding.template.workspace), label='Tree search')
