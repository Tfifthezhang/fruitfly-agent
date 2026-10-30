"""Replaceable generation and composition registration."""
from fruitfly_agent.improvement.contracts.editing import ProposalResult, GeneratorDefinition
from fruitfly_agent.improvement.contracts.validation import identifier

class AgentGenerator:
    generator_id = 'agent-editor-v1'
    required_capabilities = frozenset({'editor'})
    supports_task_sets = True

    async def propose(self, request, services):
        from fruitfly_agent.improvement.contracts.editing import ProposalResult
        candidate = await services.edit('propose', request)
        return ProposalResult((candidate,))


class AgentComposer:
    async def compose(self, request, services):
        return await services.edit('compose', request)


class GeneratorRegistry:
    """Register factories; each job receives its own generator state."""
    def __init__(self):
        self.factories = {}
        self.metadata = {}

    def register(self, generator_id, factory, *, implementation_id=None, label=None, required_capabilities=None, supports_task_sets=None):
        from fruitfly_agent.improvement.contracts.validation import identifier
        from fruitfly_agent.improvement.contracts.editing import GeneratorDefinition
        identifier(generator_id)
        if generator_id in self.factories or not callable(factory):
            raise ValueError('invalid or duplicate generator registration')
        self.factories[generator_id] = factory
        self.metadata[generator_id] = GeneratorDefinition(generator_id,
            implementation_id or getattr(factory, 'implementation_id', generator_id),
            label or getattr(factory, 'label', generator_id),
            getattr(factory, 'required_capabilities', frozenset()) if required_capabilities is None else required_capabilities,
            getattr(factory, 'supports_task_sets', False) if supports_task_sets is None else supports_task_sets)

    def definitions(self):
        return tuple(self.metadata[name] for name in sorted(self.metadata))

    def create(self, generator_id):
        if generator_id not in self.factories:
            raise ValueError('unknown candidate generator: ' + generator_id)
        generator = self.factories[generator_id]()
        if generator.generator_id != generator_id:
            raise ValueError('generator identity differs from its registration')
        if generator.required_capabilities != self.metadata[generator_id].required_capabilities:
            raise ValueError('generator capability requirements differ from its declaration')
        return generator

