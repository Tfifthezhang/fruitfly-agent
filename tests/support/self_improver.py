"""Synthetic editor experiments with real Lab loops and zero network requests."""
from dataclasses import replace
import json
import re
from unittest.mock import Mock

from fruitfly_agent.core.data_model import AssistantMessage, TextBlock, ToolCallBlock, ToolResultMessage
from fruitfly_agent.core.model_stream import AssistantMessageEventStream
from fruitfly_agent.lab.improvement.api import (WorkflowBindings, GeneratorRegistry, CandidateBundle,
    ComponentFile, HarnessSnapshot, EditReason, ProposalResult)
from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.faux_provider import FauxProvider
from tests.support.materials import _write_models
from tests.support.task_packs import install, package


class SelfRule:
    generator_id = 'self-rule'
    required_capabilities = frozenset()

    async def propose(self, request, services):
        document = request.baseline.component('improvement-editor')
        value = json.loads(document.files[0].text)
        value['invariant'] += ' STEP'
        updated = replace(document, files=(ComponentFile('instructions.txt', json.dumps(value)),))
        harness = HarnessSnapshot(tuple(updated if c.component_id == updated.component_id else c for c in request.baseline.components))
        return ProposalResult((CandidateBundle(request.plan.parent, request.baseline, harness, self.generator_id,
            (EditReason(updated.component_id, 'Synthetic supported editor edit', (request.records[0].run_id,)),)),))


class LastComposition:
    async def compose(self, request, services):
        return request.candidates[-1]


class ProceduralProvider(FauxProvider):
    """STEP in the actual editor mission controls the procedure it writes.

    This deliberately constructed response model tests binding and measurement,
    not whether any real model learns from these instructions.
    """
    def __call__(self, ctx, *, signal=None):
        self.script.append(self.reply)
        return super().__call__(ctx, signal=signal)

    def reply(self, ctx, *, signal=None):
        def text(value):
            return AssistantMessage(content=[TextBlock(text=value)], stop_reason='stop')
        def tool(name, args):
            return AssistantMessage(content=[ToolCallBlock(id='call-' + str(len(self.calls)), name=name, input=args)], stop_reason='toolUse')
        names = {t.name for t in ctx.tools}
        if 'list_files' in names:
            if 'write_file' not in names:
                result = text('{"choice":"2","reason":"Synthetic procedure comparison"}'
                    if 'Choose one existing' in ctx.system_prompt else 'NO_ENTRY')
            else:
                contents = [b.text for m in ctx.messages if isinstance(m, ToolResultMessage) for b in m.content if isinstance(b, TextBlock)]
                records = next((json.loads(v) for v in contents if v.startswith('[{') and 'run_id' in v), None)
                level = ctx.system_prompt.count('STEP')
                if records is None:
                    result = tool('read_file', {'path': 'context/executions.json'})
                elif level and 'Candidate file saved' not in contents:
                    result = tool('write_file', {'path': 'harness/base_prompt/instructions.txt', 'content': f'PROCEDURE_LEVEL={level}'})
                else:
                    reasons = ([{'component_id': 'base_prompt', 'explanation': 'Synthetic observed contrast',
                                 'evidence_ids': [records[0]['run_id']]}] if level else [])
                    result = text(json.dumps({'reasons': reasons}))
        else:
            level = re.search(r'PROCEDURE_LEVEL=(\d+)', ctx.system_prompt)
            required = 2 if 'level2' in repr(ctx.messages) else 1
            result = text('A' if level and int(level[1]) >= required else 'wrong')
        return AssistantMessageEventStream(self._message_stream(result))


def experiment_factory(root, *, uses=2):
    _write_models(root)
    for name in ('development', 'independent'):
        value = package()
        value.update(id=name, name=name, compatible_targets=['base_prompt'])
        for partition, suffix in (('train', 'training level1'), ('validation', 'selection level2'), ('holdout', 'holdout level2')):
            value[partition] = [dict(id=partition + '-1', input=name + ' ' + suffix, expected='A')]
        install(root, value)
    path = root / '.fruitfly/improvement/experiments/editor/experiment.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(id='editor', name='Synthetic editor comparison',
        development=['development'], verification=['independent'], max_verifications=uses)))
    provider = ProceduralProvider()
    providers = Mock()
    providers.create.return_value = provider
    generators = GeneratorRegistry()
    generators.register(SelfRule.generator_id, SelfRule)
    factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=providers,
        improvement_bindings=WorkflowBindings(generators=generators, composer=lambda *args: LastComposition()))
    factory.configuration.save()
    factory.reload_configuration()
    request = WorkflowRequest(component_ids=('improvement-editor',), generator_id=SelfRule.generator_id,
        execution_id='improver-comparison', task_pack_id='editor', verification='scored', scope='persistent',
        max_model_calls=512, max_executions=256)
    return factory, provider, request
