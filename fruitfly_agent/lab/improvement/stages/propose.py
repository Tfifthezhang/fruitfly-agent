"""One independent research stage over injected capabilities."""
from dataclasses import asdict
from fruitfly_agent.improvement.contracts.activities import ActivityResult
from .context import readable_context
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.stages.operations import run_stage
from fruitfly_agent.improvement.stages.services import GeneratorServices

def proposal_request(batch, plan, baseline, *, context=()):
    """Use immutable historical observations without inventing search evaluations."""
    from fruitfly_agent.improvement.contracts.editing import ResearchProposalRequest
    return ResearchProposalRequest(plan, batch.tasks, baseline, batch.records, context)

async def propose(ports, spec, inputs):
    if ports.proposal is None:
        raise ValueError('register a ProposalStage before proposing')
    from fruitfly_agent.improvement.contracts.components import HarnessSnapshot
    batch = ports.input_batch(inputs.batches)
    baseline = HarnessSnapshot.from_dict(ports.read(inputs.harness))
    context = list(readable_context(ports, inputs))
    context.append(ports.put('observations.json', batch.observations, 'input'))
    inherited = [resource for resource in inputs.evidence
                 if resource.path.rsplit('/', 1)[-1] == 'selection.json']
    if len(inherited) > 1:
        raise ValueError('propose accepts one organized material plan')
    if inherited:
        plan = ports.read(inherited[0])
        if plan.get('implementation_id') == 'focused-group-material-v1':
            expected = {(record.run_id, record.task_id) for record in batch.records}
            selected = [(row['run_id'], row['task_id']) for row in plan['selected']]
            if set(selected) != expected or len(selected) != len(expected):
                raise ValueError('organized material scope differs from the proposal batch')
            context = [resource for resource in context if resource != inherited[0]]
            context.append(ports.put('selection.json', plan, 'input'))
        else:
            inherited = []
    if not inherited and getattr(ports, 'select_evidence', None):
        context.extend(ports.select_evidence(batch))
    request = proposal_request(batch, ports.plan, baseline, context=tuple(context))
    ports.proposal.components.configure(ports.plan.component_options)
    ports.proposal.components.validate(baseline)
    generator = ports.proposal.generators.create(ports.plan.generator_id)
    if not getattr(generator, 'supports_task_sets', False):
        raise ValueError('generator does not support batch evidence')
    async with ports.create_services() as services:
        services.own(generator)
        result = await run_stage(services, 'propose', lambda: generator.propose(request, GeneratorServices(services)))
        for candidate in result.candidates:
            ports.proposal.validate(candidate, plan=ports.plan, baseline=baseline, records=request.records)
        return ActivityResult((ports.put('proposal.json', asdict(result)),
            ports.put('decision.json', asdict(result.decision) if result.decision is not None else
                {'kind': 'not_reported', 'explanation': 'The registered generator supplied no decision.'}),
            *(r for r in context if r.path == 'selection.json')))
