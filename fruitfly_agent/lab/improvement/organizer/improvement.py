"""Apply an authorized organizer I candidate to isolated organization execution."""
from .instructions import instruction_target
from .methods.layered.algorithm import LayeredOrganizer


def candidate_organizer(config, artifacts, document, *, options, baseline=None, settings=None):
    """Construct a trial role; validation is not verification or activation."""
    owner = instruction_target(baseline)
    # Reuse the shared parameter adapter to decode the candidate's protected I file.
    from ..components.text import TextComponentAdapter
    adapter = TextComponentAdapter(owner, 'improvement-instructions')
    adapter.validate(document)
    text = adapter.to_text(document)
    owner.validate_change(text, options)
    return LayeredOrganizer(config, artifacts, instructions=owner.parse(text), settings=settings)


def install_trial(context, request, registry, services):
    """An organizer I study must apply its candidate to actual inner reading."""
    if 'improvement-organizer' not in context.plan.component_ids:
        return
    from dataclasses import replace
    from fruitfly_agent.improvement.contracts.organization import OrganizationRequest
    from fruitfly_agent.improvement.contracts.lifecycle import ContextContribution
    from ..components.text import TextComponentAdapter
    from .instructions import OrganizerInstructions
    current = OrganizerInstructions(**(context.system_settings or {}).get('organizer', {}).get('instructions', {}))
    document = request.candidate.component('improvement-organizer')
    organizer = services.own(candidate_organizer(context.organizer_config or context.editor_config,
        context.artifacts, document, baseline=current,
        options=context.plan.component_options.get('improvement-organizer', {}), settings=context.evidence_settings))
    owner = instruction_target(organizer.instructions)
    registry.adapters['improvement-organizer'] = TextComponentAdapter(owner, 'improvement-instructions')
    async def organize(event):
        records = tuple(services.state.records)
        view = await organizer.organize(OrganizationRequest((request.task,), records), services)
        return ContextContribution(tuple(replace(r, kind='input') for r in view.resources))
    services.hooks.register('before_proposal', organize, active=True, required=True,
        identity='organizer-i-trial')
