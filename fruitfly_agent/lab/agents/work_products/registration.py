"""One H owner declares durable collaboration tools and their editable guidance."""
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, MechanismEffects, ParameterDescriptor
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from fruitfly_agent.lab.catalog.classification import AGENTS
from .improvement import register
from fruitfly_agent.runtime_spec.documents import parameter_default
from .methods.managed.algorithm import install_work_products

RESOURCE = ('fruitfly_agent.lab.agents.work_products.methods.managed', 'defaults.yaml')


def definition():
    instructions = ('checkpoint', 'catalog', 'read', 'patch')
    parameters = tuple(ParameterDescriptor(name, 'string', name.capitalize(), 'Work product tool guidance.',
        parameter_default(*RESOURCE, 'instructions.' + name)) for name in instructions)
    parameters += (ParameterDescriptor('page_characters', 'integer', 'Read page', 'Characters per default working-file read.',
        parameter_default(*RESOURCE, 'settings.page_characters'), minimum=1, maximum=24000),
        ParameterDescriptor('directory_entries', 'integer', 'Directory page', 'Entries per default work directory page.',
        parameter_default(*RESOURCE, 'settings.directory_entries'), minimum=1, maximum=100))
    parameters += (ParameterDescriptor('pressure_ratio', 'number', 'Checkpoint pressure',
        'Input occupancy fraction that requests a checkpoint before more material expansion.',
        parameter_default(*RESOURCE, 'settings.pressure_ratio'), minimum=0.1, maximum=1.0),)
    return register(MechanismDefinition(MechanismDescriptor('work-products', 'Work products',
        'Persist attributed checkpoints and exchange bounded working files across Agent tasks.',
        contributions=(MechanismContribution('capability', 'tools'),), default_enabled=True, install_order=25,
        parameters=parameters, effects=MechanismEffects(writes_files=True,
            tools=('save_checkpoint', 'list_work_products', 'read_work_product', 'patch_checkpoint'))),
        install_work_products, role_safe=True, default_resource=RESOURCE, feature_path=(AGENTS,),
        implementation_id='work-products-v1',
        implementation_path='fruitfly_agent/lab/agents/work_products/methods/managed/algorithm.py',
        documentation_path='fruitfly_agent/lab/agents/work_products/README.md',
        parameter_paths={p.name: ('instructions.' if p.name in instructions else 'settings.') + p.name for p in parameters}))
