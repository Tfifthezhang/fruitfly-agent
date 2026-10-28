"""A separately configured, budgeted model judge without candidate-edit tools."""
import json
from fruitfly_agent.core.data_model import ProviderView, UserMessage
from fruitfly_agent.improvement.contracts.live import Assessment, Metric


class ModelAssessor:
    def __init__(self, assessor_id, *, config, services, instruction, render):
        self.assessor_id = assessor_id
        self.config, self.services = config, services
        self.instruction, self.render = instruction, render

    async def assess(self, event):
        self.services.reserve('model')
        self.services.record('assessor-model-request', assessor_id=self.assessor_id, model=self.config.model)
        view = ProviderView(self.instruction, [UserMessage(content=self.render(event))], [],
            self.config.model, self.config.max_tokens)
        result = await self.services.operation(self.config.provider(view, signal=self.services.signal).result())
        if result.stop_reason != 'stop' or result.tool_calls or result.continue_turn:
            raise ValueError('assessor did not finish a tool-free judgment')
        value = json.loads(result.text)
        if not isinstance(value, dict) or set(value) != {'metrics'} or not isinstance(value['metrics'], list):
            raise ValueError('assessor must return exactly a metrics array')
        return Assessment(event.position, self.assessor_id, tuple(Metric(**m) for m in value['metrics']),
            status='final' if event.kind == 'finished' else 'provisional',
            scope='execution' if event.kind == 'finished' else 'prefix')
