"""Generic automatic workflow assembled after a selected text improver."""
from fruitfly_agent.core.mechanisms import MechanismContribution, MechanismDescriptor, MechanismEffects, ParameterDescriptor
from ..failure_processing import FAILURE_PROCESSOR_COMPONENT, FAILURE_ROLES_COMPONENT
from fruitfly_agent.lab.improvement.api import TEXT_IMPROVER_COMPONENT
from .workflow import AutomaticPolicy, AutomaticWorkflow


def definition():
    from fruitfly_agent.lab.catalog.models import MechanismDefinition
    return MechanismDefinition(
        MechanismDescriptor("automatic-text-search", "Automatic text improvement",
            "Prepare learning tasks, search against original tasks, and confirm once before human review.",
            contributions=(MechanismContribution("improvement", "context"),), install_order=77,
            parameters=(
                ParameterDescriptor("min_improvement", "number", "Minimum score gain", "Required original selection and independent score gain.", .05, minimum=.000001),
                ParameterDescriptor("max_case_regression", "number", "Allowed per-case regression", "Maximum original-task or independent-case regression.", 0.0, minimum=0.0),
                ParameterDescriptor("failure_threshold", "number", "Failure threshold", "Training scores below this value need improvement for maximization.", 1.0),
                ParameterDescriptor("material_limit", "integer", "Learning task limit", "Maximum derived or replayed learning tasks.", 4, minimum=1, maximum=12),
                ParameterDescriptor("confirmation_repeats", "integer", "Independent repeats", "Repeated baseline and candidate trials; identical inputs, fresh runs.", 1, minimum=1, maximum=5),
                ParameterDescriptor("timeout_seconds", "number", "Workflow timeout", "Whole automatic workflow deadline.", 600.0, minimum=1.0),
                ParameterDescriptor("external_trial_model_calls", "integer", "External task model allocation", "Shared main and auxiliary Provider calls per external task.", 24, minimum=1, maximum=300),
                ParameterDescriptor("external_trial_timeout_seconds", "integer", "External task deadline", "Whole external task deadline, including environment setup and verification.", 1800, minimum=1),
                ParameterDescriptor("external_timeout_seconds", "integer", "External experiment deadline", "Whole benchmark improvement deadline.", 14400, minimum=1),
            ), effects=MechanismEffects(uses_provider=True, uses_network=True, writes_files=True,
                cost_notice="One explicit search authorizes bounded baseline, learning, candidate and confirmation trials; no automatic adoption.")),
        _install, implementation_id=AutomaticWorkflow.implementation_id,
        implementation_path='fruitfly_agent/lab/improvement/automatic/workflow.py',
        documentation_path='fruitfly_agent/lab/improvement/automatic/README.md',
        requires_capabilities=frozenset({"failure-processing", "text-improver"}))


def _install(state, context, parameters):
    host = state.components[TEXT_IMPROVER_COMPONENT]
    configure = getattr(host, "configure_workflow", None)
    if not callable(configure):
        raise ValueError("selected text host does not support automatic workflows")
    configure(AutomaticWorkflow(state.components[FAILURE_PROCESSOR_COMPONENT], AutomaticPolicy(**parameters)),
              role_configs=state.components.get(FAILURE_ROLES_COMPONENT, {}))
    return state
