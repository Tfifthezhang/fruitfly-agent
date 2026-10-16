"""DreamRSI consumes a policy target and ordinary task acceptance materials."""
from dataclasses import replace
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects, ParameterDescriptor as P
from ...methods import MethodDefinition
from ...runtime.host import HostedTextImprover
from ...registration import text_budget_parameters
from ..tree_search.registration import search_parameters
from ..tree_search.target import POLICY_TARGET
from .improver import DreamRsiImprover


class PolicyTaskSource:
    def __init__(self, source, execution_target):
        self.source, self.execution_target = source, execution_target
    @property
    def default_pack_id(self):
        return self.source.default_pack_id
    def freeze(self, pack_id, target_id):
        if target_id != POLICY_TARGET:
            raise ValueError('policy tasks require the policy target')
        return replace(self.source.freeze(pack_id, self.execution_target), target_id=target_id)
    def holdout(self, pack_id):
        return self.source.holdout(pack_id)
    def source_hash(self, pack_id):
        return self.source.source_hash(pack_id)


def definition():
    from fruitfly_agent.lab.catalog.models import MechanismDefinition
    return MechanismDefinition(MechanismDescriptor('dream-rsi', 'DreamRSI',
        'Improve an exploration policy by historical replay and same-start real-search confirmation.',
        contributions=(MechanismContribution('improvement', 'workflow'),),
        parameters=(P('target', 'string', 'Policy target', 'Registered exploration policy.', POLICY_TARGET),
            P('cases_path', 'path', 'Task materials', 'Task pack or legacy training/selection JSON.', '.fruitfly/improvement/cases.json'),
            *(replace(p, default=64) if p.name == "max_metric_calls" else p for p in text_budget_parameters()), *search_parameters(),
            P('policy_revisions', 'integer', 'Policy revisions', 'Bounded model proposals for policy refinement.', 3, minimum=1, maximum=32),
            P('replay_rounds', 'integer', 'Replay rounds', 'Maximum rounds in each deterministic replay.', 64, minimum=1, maximum=512),
            P('replay_timeout_seconds', 'number', 'Replay timeout', 'Maximum seconds per policy replay sweep.', 30., minimum=.1, maximum=300),
            P('parallel_penalty', 'number', 'Parallel penalty', 'Weight in the paper replay objective.', .1, minimum=0, maximum=1),
            P('min_replay_gain', 'number', 'Minimum replay gain', 'Required historical objective gain.', .001, minimum=.000001),
            P('min_online_gain', 'number', 'Minimum real-search gain', 'Required task-score gain unless calls decrease without regression.', .01, minimum=.000001),
            P('confirmation_repeats', 'integer', 'Real-search repeats', 'Paired current/candidate searches from the same initial target.', 1, minimum=1, maximum=5),
            P('discovery_direction', 'string', 'Discovery objective', 'Fixed direction for real candidate generation.', 'Improve task performance.')),
        install_order=78, effects=MechanismEffects(uses_provider=True, uses_network=True, writes_files=True,
            cost_notice='Replay reads frozen histories. Policy proposals and real confirmation call models; no automatic adoption.')),
        lambda state, context, parameters: state, implementation_id=DreamRsiImprover.spec.implementation_id,
        requires_capabilities=frozenset({'tree-search'}),
        improvement=MethodDefinition(DreamRsiImprover.supported_roles, DreamRsiImprover.supported_schemas,
            DreamRsiImprover.required_capabilities, _bind, usage=DreamRsiImprover.usage))


def _bind(binding):
    strategy = DreamRsiImprover(binding.template.workspace, binding.target.execution_target, binding.parameters)
    host = binding.text_host(strategy, label='DreamRSI')
    host.require_confirmation = True
    host.task_source = PolicyTaskSource(host.task_source, binding.target.execution_target.snapshot().target_id)
    return host
