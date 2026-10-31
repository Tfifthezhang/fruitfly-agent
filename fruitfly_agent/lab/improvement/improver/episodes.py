"""Run one fixed-I experiment through Lab ports without a live Application."""
from copy import deepcopy
from dataclasses import asdict, replace
from typing import Literal

from ..components import ComponentRegistry, TextComponentAdapter
from fruitfly_agent.improvement.contracts.experiments import EpisodeResult
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.improvement.contracts.versions import SystemVersion, content_hash
from ..editor import AgentEditor, model_completion
from ..assessment.selection import AgentSelector
from ..assessment.inspection import ReadOnlyInspector
from ..editor.instructions import EditorInstructions, EditorInstructionTarget
from fruitfly_agent.lab.improvement.workflow import ImprovementWorkflow
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry, AgentGenerator, AgentComposer
from ..execution.file_runner import FileTaskRunner
from ..assessment.verification import CaseMeasurements


class NativeEpisodeExecutor:
    feedback: Literal['behavior', 'scored'] = 'behavior'
    def __init__(self, context, episode, parameters, *, generator_factory=AgentGenerator,
                 composer_factory=AgentComposer, runner_factory=FileTaskRunner, reference_policy=None):
        self.context, self.episode, self.parameters = context, episode, parameters
        self.generator_factory, self.composer_factory, self.runner_factory = generator_factory, composer_factory, runner_factory
        from .methods.evaluator_comparison.verification import reference_policy as native_reference
        self.reference_policy = reference_policy if reference_policy is not None else native_reference(episode)

    async def run(self, request, *, signal):
        context, params = self.context, self.parameters
        instructions = EditorInstructionTarget.parse_document(request.instructions)
        registry = deepcopy(context.components)
        registry.adapters['improvement-editor'] = TextComponentAdapter(
            EditorInstructionTarget(instructions, text=request.instructions), 'improvement-instructions')
        settings = deepcopy(context.system_settings or {})
        from ..assessment.instructions import EvaluatorInstructionTarget, EvaluatorInstructions
        from .methods.evaluator_comparison.episodes import install_candidate
        install_candidate(registry, request.improver, settings)
        search = context.workflow_settings or {}
        evidence = context.evidence_settings or {}
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
            timeouts=context.plan.timeouts, feedback=self.feedback,
            strategy_id=search.get('strategy', params.get('inner_strategy', 'harness2')), retain_experience=False)
        services = WorkflowServices(plan, signal=signal,
            record=lambda event, **fields: context.services.record(event, episode_id=request.episode_id, **fields))
        services.evidence_builder=context.services.evidence_builder
        try:
            editor = services.own(AgentEditor(context.editor_config, context.artifacts, registry, instructions=instructions,
                page_characters=evidence.get('page_characters', 12000)))
            services.editor = editor.edit
            services.completer = model_completion(context.editor_config)
            runner = services.own(self.runner_factory(context.config, registry, context.artifacts, services))
            generators = GeneratorRegistry()
            generators.register(self.generator_factory.generator_id, self.generator_factory)
            completed = context.completed_assessment_factory(services) if context.completed_assessment_factory else None
            exploration = context.exploration_factory(services) if context.exploration_factory else None
            if completed is not None:
                from ..assessment.completed import CompletedAssessmentService
                completed = CompletedAssessmentService(config=context.assessor_config or context.editor_config, artifacts=context.artifacts, services=services,
                    instructions=settings.get('evaluator', {}), evidence_settings=evidence)
            from ..workflow.mechanisms import install_workflow_mechanisms
            inner_context = replace(context, plan=plan, services=services, components=registry, system_settings=settings,
                save_record=None)
            stop_policy = install_workflow_mechanisms(inner_context)
            flow = ImprovementWorkflow(stop_policy=stop_policy,generators=generators, components=registry, runner=runner,
                artifacts=context.artifacts,
                completed_assessment=completed, exploration=exploration,
                measurements=getattr(runner, 'measurements', None),
                composer=services.own(self.composer_factory()), selector=AgentSelector(
                    ReadOnlyInspector(context.assessor_config or context.editor_config, context.artifacts, instructions=instructions, evaluator_instructions=EvaluatorInstructions(**settings.get('evaluator', {}).get('instructions', {})), evidence_settings=evidence), services))
            baseline = registry.snapshot()
            outcome = await flow.run(plan, request.task, baseline, services, experience=tuple(context.experience))
        finally:
            try:
                await services.close()
            finally:
                for kind, amount in services.used.items():
                    context.services.observe(kind, amount)
        evaluation_services = WorkflowServices(plan, signal=signal,
            record=lambda event, **fields: context.services.record(event, episode_id=request.episode_id, **fields))
        before, after = [], []
        try:
            runner = evaluation_services.own(self.runner_factory(context.config, registry, context.artifacts, evaluation_services))
            for index, case in enumerate(self.episode.evaluations):
                task = self.evaluation_task(index, case)
                values = []
                for harness in (baseline, outcome.harness):
                    evaluation_services.observe('execution')
                    record = await evaluation_services.operation(runner.execute(plan, task, harness), stage='execute')
                    if (record.status != 'completed' or record.task_id != task.task_id or record.material_id != task.material_id
                            or record.harness_id != harness.snapshot_id or record.initial_state_id != parent.state
                            or record.conditions_id != plan.conditions_id):
                        raise ValueError('episode evaluation receipt is incomplete or mismatched')
                    score = await evaluation_services.operation(
                        self.measure(runner, task, record, case, evaluation_services), stage='evaluator')
                    if not 0 <= score <= 1:
                        raise ValueError('improver comparison requires normalized scores in [0, 1]')
                    values.append(score)
                    ref = context.artifacts.put(canonical_json(asdict(record)).encode())
                    context.services.record('episode-evaluation', episode_id=request.episode_id, evidence=ref)
                before.append(values[0])
                after.append(values[0] if outcome.harness == baseline else values[1])
            return EpisodeResult(request.episode_id, outcome, services.used['model']+evaluation_services.used['model'], services.used['execution']+evaluation_services.used['execution'], tuple(before), tuple(after))
        finally:
            await evaluation_services.close()
            for kind,amount in evaluation_services.used.items():context.services.observe(kind,amount)

    def evaluation_task(self, index, case):
        return TaskMaterial(f'check-{index}', case.input, environment_id='file-workspace-v1')

    async def measure(self, runner, task, record, case, services):
        from .methods.evaluator_comparison.verification import measure
        return await measure(self.reference_policy, record.output, case, services)
