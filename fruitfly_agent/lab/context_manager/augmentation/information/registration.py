"""Information sources and shared retrieval policy registration."""
from dataclasses import replace
from fruitfly_agent.runtime_spec.documents import parameter_default
from fruitfly_agent.lab.catalog.models import define_mechanism as _definition
from fruitfly_agent.lab.catalog.models import MechanismDefinition, ParameterDescriptor, MechanismEffects
from fruitfly_agent.lab.catalog.classification import OptimizationCoverage
from fruitfly_agent.lab.catalog.assembly import AssemblyState, AssemblyContext, require_workspace_path
from typing import Any, Mapping
from fruitfly_agent.core.context import ContextStage
from fruitfly_agent.lab.catalog.classification import CONTEXT, AUGMENTATION, KNOWLEDGE, HTTP, RETRIEVAL
from fruitfly_agent.lab.catalog.adapters.parameters import editable_parameters
from fruitfly_agent.lab.catalog.adapters.resources import WorkspaceTextSnapshots
from fruitfly_agent.improvement.contracts.versions import STATE_SNAPSHOTS_COMPONENT, EXPERIMENT_BLOCKERS_COMPONENT
from . import InformationHub, create_local_knowledge_space, create_live_http_space
from .adapter import InformationRecallTransformer


def definitions():
    policy = _definition(
            "information-context",
            visible=False,
            layer="online",
            family="context",
            context_phase="augmentation",
            label="Information context",
            description="Select bounded context from independently registered information spaces.",
            install=_install_information_context,
            implementation_path='fruitfly_agent/lab/context_manager/augmentation/information/adapter.py',
            documentation_path='fruitfly_agent/lab/context_manager/augmentation/information/README.md',
            default=False,
            order=35,
            parameters=(
                ParameterDescriptor("top_k", "integer", "Maximum hits", "Maximum snippets per request.", parameter_default('fruitfly_agent.lab.context_manager.augmentation.information', 'information-context.yaml', 'settings.top_k'), minimum=1),
                ParameterDescriptor("max_chars", "integer", "Context characters", "Maximum injected information characters.", parameter_default('fruitfly_agent.lab.context_manager.augmentation.information', 'information-context.yaml', 'settings.max_chars'), minimum=1),
            ),
            default_resource=('fruitfly_agent.lab.context_manager.augmentation.information', 'information-context.yaml'),
        feature_path=(CONTEXT, AUGMENTATION, RETRIEVAL),
)
    return (editable_parameters(policy, {'top_k', 'max_chars'}),
_definition(
            "knowledge-files",
            optimization_coverage=OptimizationCoverage('shared', 'Read-only task knowledge; shared information selection controls context projection.', ('information-context',)),
            configuration_snapshot=lambda parameters, workspace: WorkspaceTextSnapshots(
                require_workspace_path(workspace, parameters['root'], name='knowledge root'), workspace).freeze(),
            layer="capability",
            family="context",
            label="Local knowledge",
            description="Search current Markdown and text documents in a local directory.",
            install=_install_knowledge_files,
            implementation_path='fruitfly_agent/lab/context_manager/augmentation/information/methods/local_knowledge/__init__.py',
            documentation_path='fruitfly_agent/lab/context_manager/augmentation/information/methods/local_knowledge/README.md',
            input_parameters=('root',),
            order=41,
            requires=frozenset({"information-context"}),
            parameters=(_path_parameter("root", parameter_default('fruitfly_agent.lab.context_manager.augmentation.information.methods.local_knowledge', 'defaults.yaml', 'root'), "Knowledge directory"),),
            default_resource=('fruitfly_agent.lab.context_manager.augmentation.information.methods.local_knowledge', 'defaults.yaml'),
        feature_path=(CONTEXT, AUGMENTATION, KNOWLEDGE),
),
_definition(
            "live-http",
            optimization_coverage=OptimizationCoverage('shared', 'External connector; shared information selection controls context projection. Frozen responses are required for trials.', ('information-context',)),
            layer="capability",
            family="context",
            label="Live HTTP information",
            description="Query a configured HTTPS text endpoint for each current question.",
            install=_install_live_http,
            implementation_path='fruitfly_agent/lab/context_manager/augmentation/information/methods/live_http/__init__.py',
            documentation_path='fruitfly_agent/lab/context_manager/augmentation/information/methods/live_http/README.md',
            input_parameters=('endpoint',),
            order=42,
            requires=frozenset({"information-context"}),
            parameters=(
                ParameterDescriptor("endpoint", "string", "HTTPS endpoint", "HTTPS URL containing one {query} placeholder.", parameter_default('fruitfly_agent.lab.context_manager.augmentation.information.methods.live_http', 'defaults.yaml', 'endpoint')),
                ParameterDescriptor("timeout_seconds", "number", "Timeout", "Maximum seconds for one request.", parameter_default('fruitfly_agent.lab.context_manager.augmentation.information.methods.live_http', 'defaults.yaml', 'timeout_seconds'), minimum=0.1, maximum=30.0),
            ),
            effects=MechanismEffects(uses_network=True, cost_notice="The configured endpoint may have its own charges."),
            default_resource=('fruitfly_agent.lab.context_manager.augmentation.information.methods.live_http', 'defaults.yaml'),
        feature_path=(CONTEXT, AUGMENTATION, HTTP),
))


def _path_parameter(name: str, default: str, label: str) -> ParameterDescriptor:
    return ParameterDescriptor(
        name,
        "path",
        label,
        "Workspace-relative path; escaping the workspace is rejected.",
        default,
    )

def _install_information_context(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    hub = InformationHub(top_k=parameters["top_k"], max_chars=parameters["max_chars"])
    transformer = InformationRecallTransformer(
        hub.pipeline,
        query_builder=hub.query_builder,
        guidance=lambda: hub.guidance,
    )
    return state.with_component("information", hub).with_context_stage(
        ContextStage("information-context", "augmentation", transformer, order=35)
    )

def _install_knowledge_files(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    root = require_workspace_path(context.workspace, parameters["root"], name="knowledge root")
    state.components["information"].register(create_local_knowledge_space(root))
    return state.with_component(STATE_SNAPSHOTS_COMPONENT,
        (*state.components.get(STATE_SNAPSHOTS_COMPONENT, ()), WorkspaceTextSnapshots(root, context.workspace)))

def _install_live_http(state: AssemblyState, context: AssemblyContext, parameters: Mapping[str, Any]) -> AssemblyState:
    state.components["information"].register(
        create_live_http_space(
            parameters["endpoint"],
            timeout=parameters["timeout_seconds"],
        )
    )
    return state.with_component(EXPERIMENT_BLOCKERS_COMPONENT,
        (*state.components.get(EXPERIMENT_BLOCKERS_COMPONENT, ()), "Live HTTP context has no frozen response snapshot"))

