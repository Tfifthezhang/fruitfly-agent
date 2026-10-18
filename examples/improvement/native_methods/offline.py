"""Exercise all three native methods through public Application ports, offline."""
import asyncio
import json
from pathlib import Path
import tempfile

from fruitfly_agent.core.data_model import AssistantMessage, TextBlock, Usage
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.catalog import MechanismSelection
from fruitfly_agent.lab.improvement.tasks import package_documents
from fruitfly_agent.providers import ProviderRegistry
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run.configuration import HarnessConfig, HarnessProfile, save_harness_config


class ScriptedProvider:
    def __init__(self, responses):
        self.responses = iter(responses)

    def __call__(self, view, *, signal=None):
        async def events():
            if signal is not None and signal.is_set():
                raise asyncio.CancelledError
            yield StreamDone(AssistantMessage(content=[TextBlock(text=next(self.responses))], stop_reason='stop',
                usage=Usage(input_tokens=10, output_tokens=5)))
        return AssistantMessageEventStream(events())


def install_materials(root):
    material = dict(schema_version=2, id='native-example', name='Native method example',
        description='Scripted lifecycle checks; not model quality evidence.',
        task_schema='single-turn-text-v1', target_schema='text-v1',
        compatible_targets=['execution-workflow', 'skill-document', 'learned-memory'],
        objective={'policy_id': 'normalized-exact-v1', 'direction': 'max'},
        files={'cases': 'cases.json', 'holdout': 'holdout.json'},
        train=[dict(id='train', input='Return the label A.', expected='A')],
        validation=[dict(id='select', input='Return the label B.', expected='B')],
        holdout=[dict(id='independent', input='Return the label C.', expected='C')])
    manifest, cases, holdout = package_documents(material)
    folder = root / '.fruitfly/improvement/task-packs/native-example'
    folder.mkdir(parents=True)
    for name, value in (('pack.json', manifest), ('cases.json', cases), ('holdout.json', holdout)):
        (folder / name).write_text(json.dumps(value), encoding='utf-8')
    (root / 'models.yaml').write_text('models:\n  offline:\n    provider: offline\n'
        '    model: scripted\n    api_key_env: OFFLINE_KEY\n    context_window: 16000\n'
        '    max_output_tokens: 1024\n', encoding='utf-8')
    save_harness_config(root / '.fruitfly/config.yaml', HarnessConfig('default', {
        'default': HarnessProfile('default', model_catalog='../models.yaml', model_profile='offline',
            mechanisms=tuple(MechanismSelection(identity) for identity in
                ('execution-workflow', 'skill-document', 'learned-memory')))}))


async def run_one(method, target, responses, parameters):
    with tempfile.TemporaryDirectory(prefix='fruitfly-native-example-') as directory:
        root = Path(directory)
        install_materials(root)
        registry = ProviderRegistry()
        registry.register('offline', lambda _spec, _key: ScriptedProvider(responses))
        factory = RunApplicationFactory(cwd=root, environment={'OFFLINE_KEY': 'offline-placeholder'},
            provider_registry=registry)
        app = AgentApplication(factory)
        try:
            await app.start()
            before = factory.system_version()
            preview = app.improvement_preview(target_id=target, method_id=method,
                pack_id='native-example', parameters=parameters)
            records = await app.improve('', preview_token=preview.preview_token)
            if len(records) != 1 or 'Passed' not in dict(records[0].evidence).get('Independent confirmation', ''):
                raise RuntimeError('Scripted method did not confirm exactly one candidate')
            if factory.system_version() != before:
                raise RuntimeError('Search changed the active runtime before adoption')
            await app.adopt_candidate(records[0].candidate_id)
            after = factory.system_version()
            expected = 'harness' if target == 'execution-workflow' else 'state'
            changed = [field for field in ('harness', 'improver', 'state')
                       if getattr(before, field) != getattr(after, field)]
            if changed != [expected]:
                raise RuntimeError('Adoption changed an undeclared system axis')
            return f'{method}: confirmed and adopted ({records[0].role} changed).'
        finally:
            await app.close()


async def run_demo():
    edit = json.dumps([dict(op='add', old='', new='Check the task requirements before answering.')])
    workflow = json.dumps({'steps': ['Solve the task.', 'Check and return only the final answer.']})
    results = []
    results.append(await run_one('workflow-search', 'execution-workflow',
        ['wrong', 'wrong', workflow, 'draft', 'A', 'draft', 'B', 'wrong', 'draft', 'C'],
        {'rounds': 1, 'reflection_steps': 0}))
    results.append(await run_one('skill-edit', 'skill-document',
        ['wrong', 'wrong', edit, 'B', 'A', 'wrong', 'C'], {'rounds': 1}))
    results.append(await run_one('memory-exploration', 'learned-memory',
        ['wrong', '[0]', 'wrong', '# Memory\nVerify the result before reporting success.', 'B', 'A', 'wrong', 'C'],
        {'rounds': 1}))
    return tuple(results)


if __name__ == '__main__':
    for line in asyncio.run(run_demo()):
        print(line)
    print('Scripted lifecycle checks; no model-quality claim.')
