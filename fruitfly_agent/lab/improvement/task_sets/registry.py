"""Source discovery is metadata-only; sources freeze their own material."""
from fruitfly_agent.improvement.contracts.validation import identifier


class TaskSetSourceRegistry:
    def __init__(self, definitions=()):
        self.entries = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition):
        identifier(definition.source_id)
        identifier(definition.implementation_id)
        if definition.source_id in self.entries or not callable(definition.freeze):
            raise ValueError('duplicate or invalid task-set source')
        self.entries[definition.source_id] = definition

    def get(self, name):
        try:
            return self.entries[name]
        except KeyError as exc:
            raise ValueError('unknown task-set source: ' + str(name)) from exc

    def freeze(self, specifications, context):
        bindings = []
        for specification in specifications:
            bindings.append(self.get(specification['source']).freeze(specification, context))
        return tuple(bindings)
