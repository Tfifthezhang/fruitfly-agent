"""One independent research stage over injected capabilities."""
from fruitfly_agent.improvement.contracts.activities import ActivityResult
from fruitfly_agent.improvement.contracts.research import ResearchBatch

async def execute(ports, spec, inputs):
    if ports.executor is None:
        raise ValueError('register an execution backend before executing')
    async with ports.create_services() as services:
        derived = []
        sink = services.sink
        def retain(event, **fields):
            if event == 'research-derived-candidate':
                derived.append(ports.put('derived-proposal.json', {'candidates': [fields['candidate']], 'stop': False}))
            sink(event, **fields)
        services.sink = retain
        # Registered composite backends own independent leaf execution clocks.
        result = await ports.executor(spec, inputs, services)
        if not isinstance(result, ResearchBatch):
            raise TypeError('research executor must return ResearchBatch')
        return ActivityResult((ports.put('batch.json', result.to_dict()), *derived))
