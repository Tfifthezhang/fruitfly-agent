"""Explicit local Agent execution for offline contract tests, never a product backend."""
import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
from uuid import uuid4

from fruitfly_agent.core import AgentLoopConfig
from fruitfly_agent.core.context.budget import forward_context_capabilities
from fruitfly_agent.core.data_model import AssistantMessage, UserMessage
from fruitfly_agent.core.extensions.hooks import HookRegistry
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.core.session import Session
from fruitfly_agent.lab.catalog import AssemblyContext, ProviderBinding, assemble_lab, builtin_catalog, MechanismSelection
from fruitfly_agent.lab.catalog.adapters.parameters import ParameterTarget
from fruitfly_agent.improvement.contracts.optimization import RetainedDocuments
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.improvement.execution.facts import attach_facts, receipt_facts, loop_fact_values
from fruitfly_agent.improvement.execution.handles import ManagedExecution


class TaskRunnerFixture:
    """Exercise the ordinary Catalog and Core with explicitly controlled test inputs."""
    capabilities = frozenset({'configuration-materialization', 'execution-config', 'execution-setup',
        'events', 'stop', 'tool:read', 'tool:write', 'tool:edit', 'tool:bash'})

    def __init__(self, config, components, artifacts, services):
        self.config, self.components, self.artifacts, self.services = config, components, artifacts, services

    async def start(self, plan, task, harness):
        identity = 'fixture-' + uuid4().hex
        return ManagedExecution(lambda journal: self._execute(plan, task, harness, identity, journal),
            execution_id=identity, version_id=harness.snapshot_id, artifacts=self.artifacts,
            record=self.services.record, process_events=True)

    async def execute(self, plan, task, harness):
        handle = await self.start(plan, task, harness)
        try:
            return await handle.result()
        finally:
            await handle.aclose()

    async def _execute(self, plan, task, harness, identity, journal):
        calls = 0
        tools_completed = 0
        owned = []
        with tempfile.TemporaryDirectory(prefix='test-agent-task-') as directory:
            root = Path(directory)
            originals = {entry.path: self.artifacts.read(entry.artifact_id) for entry in task.inputs}
            for path, data in originals.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            session = Session(root / '.fixture/session.jsonl')
            owned.append(session)
            def outputs():
                return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob('*')
                    if path.is_file() and '.fixture' not in path.relative_to(root).parts
                    and path.read_bytes() != originals.get(str(path.relative_to(root)))}
            def provider(view, *, signal=None):
                nonlocal calls
                calls += 1
                self.services.observe('model')
                journal.publish('model-request', model=view.model)
                async def events():
                    stream = self.config.provider(view, signal=signal)
                    try:
                        async for event in stream:
                            yield event
                        message = await stream.result()
                    finally:
                        await stream.aclose()
                    usage = message.usage
                    journal.publish('model-response', input_tokens=usage.input_tokens if usage else None,
                        output_tokens=usage.output_tokens if usage else None, usage_reported=usage is not None)
                    yield StreamDone(message)
                return AssistantMessageEventStream(events())
            forward_context_capabilities(provider, self.config.provider)
            async def observed(name, message, cancelled):
                nonlocal tools_completed
                tools_completed += 1
                journal.publish('tool-finished', tool_name=name, is_error=message.is_error, cancelled=cancelled)
                for path, data in outputs().items():
                    journal.publish('artifact-written', path=path, artifact_id=self.artifacts.put(data))
            catalog = builtin_catalog()
            names = {tool.name for tool in self.config.tools} or {'read', 'write', 'edit', 'bash'}
            selections = {d.descriptor.mechanism_id: MechanismSelection(d.descriptor.mechanism_id)
                for d in catalog.definitions() if d.descriptor.effects.tools and set(d.descriptor.effects.tools) <= names}
            selections['local-env'] = MechanismSelection('local-env')
            bindings = {}
            settings = {}
            projections = []
            prompt = self.config.system_prompt
            for document in harness.components:
                adapter = self.components.adapters[document.component_id]
                target = getattr(adapter, 'target', None)
                text = adapter.to_text(document) if target is not None else None
                if isinstance(target, RetainedDocuments):
                    settings[document.component_id] = target.parameter_values(text)
                elif isinstance(target, ParameterTarget):
                    values = target.parse(text)
                    selections[document.component_id] = MechanismSelection(document.component_id, parameters=values)
                elif target is not None:
                    binding = target.snapshot().binding
                    if binding.kind == 'prompt':
                        prompt = text
                    elif binding.kind == 'artifact':
                        bindings[binding.key] = self.artifacts.put(text.encode())
                        if document.role != 'I':
                            projections.append((target, text))
            for target, text in projections:
                prompt = target.prepare_trial(replace(self.config, system_prompt=prompt), text).system_prompt
            from fruitfly_agent.lab.context_manager.measurement import new_measurement_scope
            base = replace(self.config, provider=provider, tools=(), env=None, system_prompt=prompt,
                context_meter=new_measurement_scope(self.config.context_meter),
                session=session, hooks=HookRegistry(session=session), readable_resources=None,
                on_tool_result=observed, max_turns=None, max_tool_calls_per_turn=None,
                get_follow_up_messages=None, get_steering_messages=None)
            for factory in self.components.trial_setups:
                setup = self.services.own(factory(self.services))
                owned.append(setup)
                base = replace(base, hooks=base.hooks.extended(setup.hooks))
            runtime = None
            def finish(result=None):
                messages = session.canonical_messages()
                answers = [m for m in messages if isinstance(m, AssistantMessage)]
                resources = [Resource('trajectory.json', self.artifacts.put(canonical_json([
                    replace(m, provider_state=None).to_dict() if isinstance(m, AssistantMessage) else m.to_dict()
                    for m in messages]).encode()), 'application/json', 'trajectory')]
                if result is not None:
                    resources.append(Resource('projection.json', self.artifacts.put(canonical_json([
                        replace(m, provider_state=None).to_dict() if isinstance(m, AssistantMessage) else m.to_dict()
                        for m in result.messages]).encode()), 'application/json', 'diagnostic'))
                if runtime is not None:
                    for component in runtime.components.values():
                        export = getattr(component, 'execution_artifacts', None)
                        if export:
                            resources.extend(Resource(path, self.artifacts.put(data), 'application/octet-stream', 'diagnostic')
                                for path, data in export().items())
                resources.extend(Resource('deliverables/' + path, self.artifacts.put(data),
                    'application/octet-stream', 'deliverable') for path, data in outputs().items())
                from fruitfly_agent.runtime_spec import effective_execution
                if runtime is not None:
                    resources.append(Resource('runtime-execution.json', self.artifacts.put(
                        canonical_json(effective_execution(runtime.config)).encode()), 'application/json', 'diagnostic'))
                record = ExecutionRecord(identity, task.task_id, task.material_id, harness.snapshot_id,
                    plan.parent.state, plan.conditions_id, 'cancelled' if result is None else 'error' if result.is_error else 'completed',
                    answers[-1].text if answers else '', tuple(resources), calls)
                values = loop_fact_values(result.diagnostics) if result is not None else {
                    'termination_reason': 'execution_interrupted', 'diagnosable': tools_completed > 0,
                    'counters': (('tool_completed', tools_completed),)}
                return attach_facts(record, receipt_facts(record, self.artifacts, **values), self.artifacts)
            try:
                runtime = assemble_lab(base, catalog=catalog, selections=tuple(selections.values()),
                    context=AssemblyContext(root, session, base.model,
                        lambda alias, max_tokens: ProviderBinding(provider, base.model, '', base.context_window, base.max_tokens),
                        session_path=session.path, resource_sink=owned, artifact_bindings=bindings,
                        component_settings=settings,
                        artifact_reader=lambda ref: self.artifacts.read(ref).decode(), agent_hooks_from_host=self.components.agent_hooks_from_host))
                result = await run_agent_loop(runtime.config, [UserMessage(task.instruction)],
                    signal=self.services.signal, context_pipeline=runtime.context_pipeline)
                return finish(result)
            except asyncio.CancelledError:
                self.services.retain_execution(finish())
                raise
            finally:
                for value in reversed(owned):
                    if value in self.services.resources:
                        await self.services.release(value)
                        continue
                    close = getattr(value, 'aclose', None) or getattr(value, 'close', None)
                    if close:
                        result = close()
                        if hasattr(result, '__await__'):
                            await result


from fruitfly_agent.run import RunApplicationFactory
from fruitfly_agent.lab.improvement.api import StageBindings


class TaskApplicationFixture(RunApplicationFactory):
    """Register the controlled test executor explicitly at the host boundary."""
    def __init__(self, *args, **kwargs):
        bindings = kwargs.pop('improvement_bindings', None) or StageBindings()
        if bindings.runner is None:
            def runner(plan, components, artifacts, services):
                if plan != services.plan:
                    raise ValueError('runner factory requires the current RunPlan')
                return TaskRunnerFixture(self._current_runtime_config, components, artifacts, services)
            runner.capabilities = TaskRunnerFixture.capabilities
            bindings = replace(bindings, runner=runner)
        super().__init__(*args, improvement_bindings=bindings, **kwargs)


def collection_registry(rows):
    """A test declares its own collection and explicit execution capability."""
    import unicodedata
    from fruitfly_agent.lab.improvement.task_sets import TaskSetSourceRegistry
    from fruitfly_agent.improvement.contracts.task_sets import TaskSetSourceDefinition, TaskEntry, ScoreSpec, CollectionBinding
    from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
    from fruitfly_agent.improvement.contracts.experiments import ExecutionPorts
    from fruitfly_agent.improvement.contracts.versions import content_hash
    from fruitfly_agent.lab.improvement.assessment.verification import CaseMeasurements
    def freeze(spec, context):
        pack = spec['pack']
        suite = context.tasks.freeze(pack, (context.component_ids or ('base_prompt',))[0])
        entries, cases = [], {}
        objective = ScoreSpec(suite.policy_id, direction=suite.direction, **spec.get('objective', {}))
        for partition, values in (('development', suite.train), ('selection', suite.validation),
                                  ('confirmation', context.tasks.holdout(pack))):
            for case in values:
                origin = 'fixture-text:' + content_hash(unicodedata.normalize('NFC', case.input).strip())
                key = spec['id'] + '-' + content_hash(origin)[7:31]
                task = TaskMaterial(key, case.input, environment_id='controlled-test', origin='task-pack:' + pack)
                entries.append(TaskEntry(key, spec['id'], suite.source_hash, spec['id'], task, objective,
                    origin, group_id=origin, partition=partition))
                cases[key] = case
        def build(leaf):
            return ExecutionPorts(TaskRunnerFixture(leaf.config, leaf.components, leaf.artifacts, leaf.services),
                CaseMeasurements(suite.evaluation_policy, cases), retain_experience=False)
        return CollectionBinding(tuple(entries), build, lambda: context.tasks.source_hash(pack),
            suite.source_hash, TaskRunnerFixture.capabilities)
    return TaskSetSourceRegistry((TaskSetSourceDefinition('fixture', 'controlled-test-collection', freeze),))
