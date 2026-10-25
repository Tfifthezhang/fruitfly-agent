"""Register I execution through generic metadata, without host algorithm branches."""
from dataclasses import asdict

from ..contracts.experiments import (ExecutionDefinition, ExecutionParameter as P, ExecutionPorts,
    ExperimentSpec, PreparedExecution)
from ..contracts.pipeline import TaskMaterial, canonical_json
from ..contracts.versions import content_hash
from .materials import freeze, materials
from .runner import ImproverTaskRunner, TrialMeasurements
from .verification import ImproverVerification


PARAMETERS = (
    P('inner_strategy', 'Inner search strategy', 'string', 'harness2',
      description='Registered strategy used for each fixed-I episode; simple or harness2.'),
    P('inner_components', 'Inner editable components', 'string', 'base_prompt',
      description='Space-separated registered H/S IDs; I is forbidden inside an episode.'),
    P('repetitions', 'Paired repetitions', 'integer', 2, 2, 10),
    P('inner_depth', 'Inner refinement depth', 'integer', 1, 1, 3),
    P('inner_model_calls', 'Model calls per inner search', 'integer', 12, 4, 1000),
    P('inner_executions', 'Task executions per inner search', 'integer', 4, 4, 100),
    P('evaluation_model_calls', 'Model allowance per evaluation', 'integer', 1, 1, 32),
    P('max_trials', 'Development trial limit', 'integer', 8, 1, 40),
    P('min_gain', 'Minimum paired gain', 'number', 0.0, 0, 1),
    P('max_regression', 'Maximum case regression', 'number', 0.0, 0, 1),
    P('max_model_ratio', 'Maximum model-call ratio', 'number', 1.5, 0.1, 10),
)


def prepare(context, request):
    params = definition().normalize(request.parameters)
    from ..strategies import builtin_strategies
    builtin_strategies().get(params['inner_strategy'])
    if request.component_ids != ('improvement-editor',) or request.input_paths:
        raise ValueError('editor comparison changes only the registered I target; episode packs own inputs')
    if request.feedback != 'scored':
        raise ValueError('editor comparison requires measured feedback')
    ids = tuple(params['inner_components'].split())
    baseline = context.components.snapshot()
    for name in ids:
        document = baseline.component(name)
        if document.role == 'I':
            raise ValueError('inner experiments cannot modify I')
        required: frozenset[str] = getattr(context.components.adapters[name], 'required_capabilities', frozenset())
        from ..execution.file_runner import FileTaskRunner
        if required - FileTaskRunner.capabilities:
            raise ValueError('inner file runner lacks component capabilities')
    frozen = freeze(context, request.material_id, ids[0] if ids else 'base_prompt')
    if (request.scope == 'persistent' and context.remaining_verification is not None and
            context.remaining_verification(frozen.verification_key, frozen.max_verifications) == 0):
        raise ValueError('independent verification use limit exhausted; provide new material')
    for e in (*frozen.development, *frozen.verification):
        for name in ids:
            context.tasks.freeze(e.pack_id, name)
    spec = ExperimentSpec(frozen.source_id, baseline.snapshot_id, context.plan.parent.state,
        content_hash(canonical_json({'plan': asdict(context.plan), 'source': frozen.source_id, 'parameters': params})), ids,
        params['repetitions'])
    task = TaskMaterial('editor-comparison',
        'Improve the editor instructions using the supplied development trials. '
        'Only propose, invariant, domain and compose may change; preserve system, select and reflect. '
        'Judge changes by downstream improvement evidence, not wording or prompt length.',
        environment_id='improver-comparison-v1', origin='experiment:' + request.material_id)
    prepared = PreparedExecution(task, frozen.source_id,
        (('Experiment', frozen.name), ('Inner components', ', '.join(ids)),
         ('Repetitions', str(params['repetitions'])), ('Maximum depth', '2'),
         ('Frozen editor fields', 'system, select, reflect'), ('Experience', 'Frozen; no experiment writes'),
         ('Independent verification uses', str(frozen.max_verifications))),
        lambda: freeze(context, request.material_id, ids[0]).source_id, (frozen, params, spec))
    def allocation(episodes):
        checks = sum(2 * len(e.evaluations) for e in episodes)
        return {'model': params['repetitions'] * (len(episodes) * params['inner_model_calls'] + checks * params['evaluation_model_calls']),
                'execution': params['repetitions'] * (len(episodes) * params['inner_executions'] + checks)}
    dev, confirmation = allocation(frozen.development), allocation(frozen.verification)
    prepared.minimum_budget = {k: 2 * dev[k] + (2 * confirmation[k] if request.scope == 'persistent' else 0)
                               + (3 if k == 'model' else 0) for k in dev}
    return prepared


def build(context, prepared):
    frozen, params, spec = prepared.private
    runner = context.services.own(ImproverTaskRunner(context, frozen, params, spec))
    verifier = ImproverVerification(runner, context.claim_verification)
    allocation = runner.allocation('verification')
    reserve = {k: 2 * v for k, v in allocation.items()} if context.plan.purpose == 'persistent' else {'model': 0, 'execution': 0}
    return ExecutionPorts(runner, TrialMeasurements(runner), verifier, verification_reserve=reserve, retain_experience=False)


def definition():
    return ExecutionDefinition('improver-comparison', 'Editor self-improvement', 'improver-comparison-v1',
        frozenset({'I'}), ImproverTaskRunner.capabilities, materials, prepare, build, PARAMETERS,
        'Runs bounded nested improvement experiments and private comparisons. Calls may incur charges. '
        'Set a root budget large enough for repeated search and reserved final verification.',
        defaults=(('verification', 'scored'), ('scope', 'persistent'), ('max_model_calls', 512), ('max_executions', 256)))
