"""Run one fixed-I experiment through Lab ports without a live Application."""
from copy import deepcopy
from dataclasses import asdict, replace
from inspect import isawaitable

from ..components import ComponentRegistry, TextComponentAdapter
from ..contracts.experiments import EpisodeResult
from ..contracts.pipeline import RunPlan, TaskMaterial, canonical_json
from ..contracts.versions import SystemVersion, content_hash
from ..editor import AgentEditor, AgentSelector, model_completion
from ..editor.instructions import EditorInstructions, EditorInstructionTarget
from ..workflow import ImprovementWorkflow, WorkflowServices, GeneratorRegistry, AgentGenerator, AgentComposer
from ..workflow.execution import FileTaskRunner
from ..verification import CaseMeasurements


class NativeEpisodeExecutor:
    def __init__(self, context, episode, parameters, *, generator_factory=AgentGenerator,
                 composer_factory=AgentComposer, runner_factory=FileTaskRunner):
        self.context, self.episode, self.parameters = context, episode, parameters
        self.generator_factory, self.composer_factory, self.runner_factory = generator_factory, composer_factory, runner_factory

    async def run(self, request, *, budget, signal):
        context, params = self.context, self.parameters
        instructions = EditorInstructions.parse(request.instructions)
        registry = deepcopy(context.components)
        registry.adapters['improvement-editor'] = TextComponentAdapter(
            EditorInstructionTarget(instructions, text=request.instructions), 'improvement-instructions')
        if any(registry.snapshot().component(name).role == 'I' for name in request.component_ids):
            raise ValueError('inner experiments cannot modify I')
        parent = SystemVersion(context.plan.parent.harness, content_hash(request.instructions), context.plan.parent.state)
        plan = RunPlan(request.episode_id, parent, request.component_ids,
            generator_id=self.generator_factory.generator_id, mode='sequential', depth=params['inner_depth'],
            max_model_calls=params['inner_model_calls'], max_executions=params['inner_executions'],
            operation_timeout=context.plan.operation_timeout)
        selection = budget.child({'model': params['inner_model_calls'], 'execution': params['inner_executions']})
        services = WorkflowServices(plan, budget=selection,
            record=lambda event, **fields: context.services.record(event, episode_id=request.episode_id, **fields))
        try:
            editor = services.own(AgentEditor(context.editor_config, context.artifacts, registry, instructions=instructions))
            services.editor = editor.edit
            services.completer = model_completion(context.editor_config)
            runner = services.own(self.runner_factory(context.config, registry, context.artifacts, services))
            generators = GeneratorRegistry()
            generators.register(self.generator_factory.generator_id, self.generator_factory)
            flow = ImprovementWorkflow(generators=generators, components=registry, runner=runner,
                composer=services.own(self.composer_factory()), selector=AgentSelector(editor, services))
            baseline = registry.snapshot()
            outcome = await flow.run(plan, request.task, baseline, services, experience=tuple(context.experience))
        finally:
            await services.close()
        # Evaluator has separate remaining quota. It is never supplied to the editor.
        evaluation_services = WorkflowServices(plan, budget=budget,
            record=lambda event, **fields: context.services.record(event, episode_id=request.episode_id, **fields))
        before, after = [], []
        try:
            runner = evaluation_services.own(self.runner_factory(context.config, registry, context.artifacts, evaluation_services))
            for index, case in enumerate(self.episode.evaluations):
                task = TaskMaterial(f'check-{index}', case.input, environment_id='file-workspace-v1')
                values = []
                for harness in (baseline, outcome.harness):
                    check_budget = budget.child({'model': params['evaluation_model_calls'], 'execution': 1})
                    try:
                        with evaluation_services.phase(check_budget):
                            evaluation_services.reserve('execution')
                            record = await evaluation_services.operation(runner.execute(plan, task, harness))
                    finally:
                        check_budget.close()
                    if (record.status != 'completed' or record.task_id != task.task_id or record.material_id != task.material_id
                            or record.harness_id != harness.snapshot_id or record.initial_state_id != parent.state
                            or record.conditions_id != plan.conditions_id):
                        raise ValueError('episode evaluation receipt is incomplete or mismatched')
                    score = self.episode.suite.evaluation_policy.score(record.output, case)
                    if isawaitable(score):
                        score = await evaluation_services.operation(score)
                    if not 0 <= score.score <= 1:
                        raise ValueError('improver comparison requires normalized scores in [0, 1]')
                    values.append(score.score)
                    ref = context.artifacts.put(canonical_json(asdict(record)).encode())
                    context.services.record('episode-evaluation', episode_id=request.episode_id, evidence=ref)
                before.append(values[0])
                after.append(values[0] if outcome.harness == baseline else values[1])
            return EpisodeResult(request.episode_id, outcome, budget.used['model'], budget.used['execution'], tuple(before), tuple(after))
        finally:
            await evaluation_services.close()
