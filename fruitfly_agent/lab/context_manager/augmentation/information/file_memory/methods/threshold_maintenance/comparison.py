"""Fixed-depth I comparison measures the downstream memories it generates."""
from copy import deepcopy
from dataclasses import replace
import json

from fruitfly_agent.improvement.contracts.experiments import EpisodeResult
from fruitfly_agent.improvement.contracts.pipeline import ImprovementOutcome
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.components import HarnessSnapshot
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.lab.improvement.components import TextComponentAdapter
from fruitfly_agent.lab.improvement.editor import model_completion
from fruitfly_agent.lab.improvement.improver import registration as comparison_host
from .algorithm import ThresholdMaintenance
from .config import MaintenanceConfig


def selected_operation(component_ids):
    if len(component_ids) != 1 or component_ids[0] not in {'memory-extractor', 'memory-consolidator'}:
        raise ValueError('memory comparison requires exactly one editor operation')
    return 'extract' if component_ids[0] == 'memory-extractor' else 'consolidate'


class MemoryEpisodeExecutor:
    """Private scoring sees answers; memory generation receives training input only."""
    def __init__(self, context, episode, parameters):
        self.context, self.episode, self.parameters = context, episode, parameters

    async def run(self, request, *, signal):
        context = self.context
        operation = selected_operation(context.component_ids)
        registry = deepcopy(context.components)
        base = request.baseline
        owner = registry.adapters['memory-library'].target
        values = json.loads(registry.adapters['memory-library'].to_text(base.component('memory-library')))
        documents = values['content']['documents']
        prompts = {}
        for key in ('memory-extractor', 'memory-consolidator'):
            adapter = registry.adapters[key]
            document = request.improver.component(key)
            prompts[key] = adapter.target.parse(adapter.to_text(document))['prompt']
        policy = registry.adapters['memory-maintenance']
        parameters = policy.target.parse(policy.to_text(base.component('memory-maintenance')))
        config = MaintenanceConfig(**{k: v for k, v in parameters.items() if k != 'model_profile'})
        worker = ThresholdMaintenance(config, prompts['memory-extractor'], prompts['memory-consolidator'],
            lambda: (_ for _ in ()).throw(ValueError('comparison uses injected completion')))
        session = 'study-' + content_hash(request.task.instruction)[7:31]
        evidence = [{'identity': session + ':user-1', 'session_id': session, 'message_id': 'user-1',
            'chars': len(request.task.instruction), 'completed': True}]
        checkpoint = {'pending': {}, 'processed': 0, 'consolidated_turns': 0, 'evidence': evidence}
        # The study fixes timing. Selecting a consolidation prompt measures that
        # operation directly instead of waiting for production counters.
        work = {'operation': operation, 'entries': json.loads(documents), 'processed': 0, 'turns': 1}
        plan = RunPlan(request.episode_id, context.plan.parent, ('memory-library',),
            timeouts=context.plan.timeouts, retain_experience=False)
        services = WorkflowServices(plan, signal=signal, complete=model_completion(context.editor_config),
            record=lambda event, **fields: context.services.record(event, episode_id=request.episode_id, **fields))
        try:
            changed, _, _ = await services.operation(worker.generate(work, checkpoint,
                lambda row: request.task.instruction, complete=services.complete), stage='editor')
            after = base
            if changed is not None:
                entries = owner.validate_documents(json.loads(changed))
                trial_target = owner.with_state_change(entries)
                adapter = TextComponentAdapter(trial_target, 'mechanism-parameters')
                registry.adapters['memory-library'] = adapter
                import yaml
                document = base.component('memory-library')
                value = yaml.safe_load(document.files[0].text)
                value['parameters']['content']['documents'] = changed
                from fruitfly_agent.improvement.contracts.components import ComponentFile
                modified = replace(document, files=(ComponentFile('parameters.yaml', yaml.safe_dump(value)),))
                adapter.validate(modified)
                after = HarnessSnapshot(tuple(modified if c.component_id == 'memory-library' else c for c in base.components))
            runner = services.own(context.runner_factory(plan, registry, context.artifacts, services))
            policy = self.episode.suite.evaluation_policy
            before_scores, after_scores, records = [], [], []
            for index, case in enumerate(self.episode.evaluations):
                from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
                task = TaskMaterial('memory-check-' + str(index), case.input)
                scores = []
                for harness in (base, after):
                    services.observe('execution')
                    record = await services.operation(runner.execute(plan, task, harness), stage='execute')
                    if (record.status != 'completed' or record.harness_id != harness.snapshot_id
                            or record.task_id != task.task_id or record.material_id != task.material_id
                            or record.initial_state_id != plan.parent.state or record.conditions_id != plan.conditions_id):
                        raise ValueError('memory comparison execution receipt mismatch')
                    result = policy.score(record.output, case)
                    from inspect import isawaitable
                    if isawaitable(result):
                        result = await services.operation(result, stage='evaluator')
                    if not 0 <= result.score <= 1:
                        raise ValueError('memory comparison requires normalized scores')
                    scores.append(result.score)
                    records.append(record)
                before_scores.append(scores[0]); after_scores.append(scores[1])
            outcome = ImprovementOutcome(plan, request.task, records[-1], after, (), tuple(records), None)
            return EpisodeResult(request.episode_id, outcome, services.used['model'], services.used['execution'],
                tuple(before_scores), tuple(after_scores))
        finally:
            await services.close()
            for kind, amount in services.used.items():
                context.services.observe(kind, amount)


def definition():
    from fruitfly_agent.lab.improvement.improver.materials import freeze, materials
    from fruitfly_agent.improvement.contracts.experiments import ExecutionParameter
    from fruitfly_agent.lab.improvement.improver.runner import ImproverTaskRunner
    from fruitfly_agent.improvement.contracts.experiments import ExecutionDefinition
    capabilities = ImproverTaskRunner.capabilities | frozenset({'configuration-materialization', 'memory-maintenance-comparison'})
    def validate(context, frozen, ids):
        if ids != ('memory-library',):
            raise ValueError('memory comparison changes only the downstream memory library')
        selected_operation(context.component_ids)
        for key in ('memory-maintenance', 'memory-extractor', 'memory-consolidator', 'memory-library'):
            context.components.snapshot().component(key)
        if context.runner_factory is None:
            raise ValueError('memory comparison requires a registered downstream task runner')
    def prepare(context, request):
        return comparison_host.prepare(context, request, execution=definition(), freeze_materials=freeze,
            inner_capabilities=getattr(context.runner_factory, 'capabilities', frozenset()), validate_materials=validate)
    def build(context, prepared):
        return comparison_host.build(context, prepared, episode_factory=MemoryEpisodeExecutor)
    parameters = tuple(replace(p, default='memory-library') if p.name == 'inner_components' else p
        for p in comparison_host.PARAMETERS)
    return ExecutionDefinition('memory-maintenance-comparison', 'Memory editor comparison',
        'memory-maintenance-comparison-v1', frozenset({'I'}), capabilities, materials, prepare, build,
        parameters, defaults=(('scope', 'persistent'),))
