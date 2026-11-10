"""One independent research stage over injected capabilities."""
from dataclasses import asdict
from fruitfly_agent.improvement.contracts.activities import ActivityResult
from .context import readable_context
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.organization import OrganizationRequest

async def organize(ports, spec, inputs):
    if ports.organizer is None:
        raise ValueError('register an Organizer role before organizing')
    batch = ports.input_batch(inputs.batches)
    context = (*readable_context(ports, inputs),
        ports.put('observations.json', batch.observations, 'input'))
    async with ports.create_services() as services:
        view = await ports.organizer.organize(OrganizationRequest(batch.tasks, batch.records,
            spec.parameters.get('instruction') or 'Organize the supplied batch for reading.', context), services)
        return ActivityResult((ports.put('view.json', asdict(view)), *view.resources))
