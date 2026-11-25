"""One independent research stage over injected capabilities."""
from fruitfly_agent.improvement.contracts.activities import ActivityResult
from ..assessment.methods.measured import compare_measured
from ..assessment.methods.model.research_comparison import compare_model
from .context import readable_context


async def compare(ports, spec, inputs):
    policy = spec.parameters.get('measured_policy')
    if policy is not None and len(inputs.batches) != 2:
        raise ValueError('measured comparison requires before and after batches')
    batches = [ports.read_batch(resource) for resource in inputs.batches]
    input_ids = [resource.artifact_id for resource in inputs.batches]
    if spec.parameters.get('comparison_method', 'measured') == 'model' and policy is None:
        result = await compare_model(ports, batches, context=readable_context(ports, inputs),
                                     input_ids=input_ids, policy=spec.parameters.get('role_identity', {}))
    elif policy is not None:
        result = compare_measured(batches[0], batches[1], policy, input_ids)
    else:
        if len(batches) != 2:
            raise ValueError('measured comparison requires before and after batches')
        from ..assessment.methods.measured.policy import compare_batches
        scope_id = spec.parameters.get('task_scope_id')
        if scope_id is not None and scope_id not in input_ids:
            raise ValueError('task_scope must reference an input batch')
        result = compare_batches(batches[0], batches[1], input_ids,
            settings=spec.parameters.get('comparison_settings'),
            scope=batches[input_ids.index(scope_id)] if scope_id is not None else None,
            read=getattr(ports, 'read', None))
    outputs = [ports.put('comparison.json', result)]
    if result['method'] == 'measured' and getattr(ports, 'put_text', None):
        from ..assessment.methods.measured.reporting import exports
        outputs.extend(ports.put_text(path, text, media) for path, (text, media) in exports(result).items())
    return ActivityResult(tuple(outputs))
