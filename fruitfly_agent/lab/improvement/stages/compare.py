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
    if policy is None:
        result = await compare_model(ports, batches, context=readable_context(ports, inputs),
                                     input_ids=input_ids, policy=spec.parameters.get('role_identity', {}))
    else:
        result = compare_measured(*batches, policy, input_ids)
    return ActivityResult((ports.put('comparison.json', result),))
