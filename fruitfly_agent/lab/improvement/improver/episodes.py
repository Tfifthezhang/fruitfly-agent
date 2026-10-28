"""Run one fixed-I experiment through Lab ports without a live Application."""
from copy import deepcopy
from dataclasses import asdict, replace
from inspect import isawaitable
from typing import Literal

from ..components import ComponentRegistry, TextComponentAdapter
from fruitfly_agent.improvement.contracts.experiments import EpisodeResult
from fruitfly_agent.improvement.contracts.pipeline import RunPlan, TaskMaterial, canonical_json
from fruitfly_agent.improvement.contracts.versions import SystemVersion, content_hash
from ..editor import AgentEditor, model_completion
from ..assessment.selection import AgentSelector
from ..assessment.inspection import ReadOnlyInspector
from ..editor.instructions import EditorInstructions, EditorInstructionTarget
from ..workflow import ImprovementWorkflow, WorkflowServices, GeneratorRegistry, AgentGenerator, AgentComposer
from ..execution.file_runner import FileTaskRunner
from ..assessment.verification import CaseMeasurements


class NativeEpisodeExecutor:
    feedback: Literal['behavior', 'scored'] = 'behavior'
    def __init__(self, context, episode, parameters, *, generator_factory=AgentGenerator,
                 composer_factory=AgentComposer, runner_factory=FileTaskRunner):
        self.context, self.episode, self.parameters = context, episode, parameters
        self.generator_factory, self.composer_factory, self.runner_factory = generator_factory, composer_factory, runner_factory

    async def run(self, request, *, budget, signal):
        context, params = self.context, self.parameters
        instructions, calls, turns = EditorInstructionTarget.parse_document(request.instructions)
        registry = deepcopy(context.components)
        registry.adapters['improvement-editor'] = TextComponentAdapter(
            EditorInstructionTarget(instructions, max_tool_calls=calls, max_turns=turns, text=request.instructions), 'improvement-instructions')
        settings = deepcopy(context.system_settings or {})
        from ..components.configuration import ImprovementSettingsTarget
        for key in ('feedback', 'search'):
            name = 'improvement-' + key
            if request.improver is not None and name in registry.adapters:
                document = request.improver.component(name)
                target = ImprovementSettingsTarget(key, registry.adapters[name].target.parse(document.files[0].text))
                settings[key] = target.parameters
                registry.adapters[name] = TextComponentAdapter(target, 'improvement-settings')
        search = settings.get('search', {})
        feedback = settings.get('feedback', {})
        depth = search.get('rounds', params['inner_depth'])
        if depth > params['inner_depth']:
            raise ValueError('candidate search rounds exceed fixed episode depth allowance')
        if any(registry.snapshot().component(name).role == 'I' for name in request.component_ids):
            raise ValueError('inner experiments cannot modify I')
        parent = SystemVersion(context.plan.parent.harness,
            request.improver.snapshot_id if request.improver is not None else content_hash(request.instructions),
            context.plan.parent.state)
        plan = RunPlan(request.episode_id, parent, request.component_ids,
            generator_id=self.generator_factory.generator_id, mode='sequential', depth=depth,
            max_model_calls=params['inner_model_calls'], max_executions=params['inner_executions'],
            operation_timeout=context.plan.operation_timeout, feedback=self.feedback,
            strategy_id=search.get('strategy', params.get('inner_strategy', 'harness2')), retain_experience=False)
        selection = budget.child({'model': params['inner_model_calls'], 'execution': params['inner_executions']})
        services = WorkflowServices(plan, budget=selection,
            record=lambda event, **fields: context.services.record(event, episode_id=request.episode_id, **fields))
        try:
            editor = services.own(AgentEditor(context.editor_config, context.artifacts, registry, instructions=instructions,
                max_tool_calls=calls, max_turns=turns,
                page_characters=feedback.get('evidence', {}).get('page_characters', 12000),
                projection=feedback.get('evidence', {}).get('projection', 'granted-full'),
                    access_mode=feedback.get('evidence', {}).get('access_mode', 'search')))
            services.editor = editor.edit
            services.completer = model_completion(context.editor_config)
            runner = services.own(self.runner_factory(context.config, registry, context.artifacts, services))
            generators = GeneratorRegistry()
            generators.register(self.generator_factory.generator_id, self.generator_factory)
            completed = context.completed_assessment_factory(services) if context.completed_assessment_factory else None
            exploration = context.exploration_factory(services) if context.exploration_factory else None
            if feedback:
                from ..assessment.completed import CompletedAssessmentService
                from ..assessment.configuration import ProcessAssessmentSettings
                from ..assessment.registry import builtin_completed_assessors
                assessment_values = {key: value for key, value in feedback['process_assessment'].items() if key != 'model_role'}
                completed = CompletedAssessmentService(ProcessAssessmentSettings(**assessment_values),
                    config=context.assessor_config or context.editor_config, artifacts=context.artifacts, services=services,
                    registry=completed.registry if completed is not None else builtin_completed_assessors(), instructions=feedback)
            if search:
                from ..assessment.configuration import ProcessAssessmentSettings
                from ..strategies.exploration import builtin_explorations, validate_process_configuration, ExplorationSettings
                from ..assessment.registry import builtin_completed_assessors
                validate_process_configuration(completed.settings if completed is not None else ProcessAssessmentSettings(),
                    ExplorationSettings(search['exploration']), builtin_completed_assessors(), builtin_explorations())
                exploration = builtin_explorations().create(search['exploration'], own=services.own)
            from ..workflow.mechanisms import install_workflow_mechanisms
            inner_context = replace(context, plan=plan, services=services, components=registry, system_settings=settings,
                save_record=None)
            stop_policy = install_workflow_mechanisms(inner_context)
            flow = ImprovementWorkflow(stop_policy=stop_policy,generators=generators, components=registry, runner=runner,
                artifacts=context.artifacts,
                completed_assessment=completed, exploration=exploration,
                measurements=getattr(runner, 'measurements', None),
                composer=services.own(self.composer_factory()), selector=AgentSelector(
                    ReadOnlyInspector(context.assessor_config or context.editor_config, context.artifacts, instructions=instructions), services))
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
                task = self.evaluation_task(index, case)
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
                    score = await self.measure(runner, task, record, case, evaluation_services)
                    if not 0 <= score <= 1:
                        raise ValueError('improver comparison requires normalized scores in [0, 1]')
                    values.append(score)
                    ref = context.artifacts.put(canonical_json(asdict(record)).encode())
                    context.services.record('episode-evaluation', episode_id=request.episode_id, evidence=ref)
                before.append(values[0])
                after.append(values[0] if outcome.harness == baseline else values[1])
            return EpisodeResult(request.episode_id, outcome, budget.used['model'], budget.used['execution'], tuple(before), tuple(after))
        finally:
            await evaluation_services.close()

    def evaluation_task(self, index, case):
        return TaskMaterial(f'check-{index}', case.input, environment_id='file-workspace-v1')

    async def measure(self, runner, task, record, case, services):
        score = self.episode.suite.evaluation_policy.score(record.output, case)
        if isawaitable(score):
            score = await services.operation(score)
        return score.score
