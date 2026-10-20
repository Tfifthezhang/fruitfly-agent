"""Capability-driven component workflow menu; no concrete generator branches."""
from dataclasses import replace
import shlex

from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest
from fruitfly_agent.interactive.contracts.evaluation import BenchmarkImprovementRequest
from fruitfly_agent.interactive.terminal.io.menu import MenuRow


class WorkflowPanel:
    def __init__(self, *, client, configuration, choose, read, confirm, report, execute, history, direction='', benchmark=None):
        self.client, self.configuration = client, configuration
        self.choose, self.read, self.confirm, self.report = choose, read, confirm, report
        self.execute, self.history = execute, history
        self.benchmark, self.external = benchmark, None
        components = tuple(c.component_id for c in configuration.components if c.available)
        generators = tuple(c.choice_id for c in configuration.generators if c.available)
        self.request = WorkflowRequest(component_ids=components[:1],
            generator_id=generators[0] if generators else '', direction=direction)
        self.request = replace(self.request, **{p.name: p.value for p in configuration.parameters
            if p.name in {'width', 'depth', 'max_model_calls', 'max_executions', 'operation_timeout'}})

    async def run(self):
        while True:
            value = self.request
            rows = (
                MenuRow('Task', (' / '.join(self.external[:2]) if self.external else (value.task_pack_id or value.instruction)) or 'Choose task material'),
                MenuRow('Input files', ', '.join(value.input_paths) or 'No files selected'),
                MenuRow('Editable components', ', '.join(value.component_ids) or 'Select components'),
                MenuRow('Candidate generator', value.generator_id or 'No available generator'),
                MenuRow('Exploration', f'{value.mode} · width {value.width} · depth {value.depth}'),
                MenuRow('Budget', f'{value.max_model_calls} model calls · {value.max_executions} executions · {value.operation_timeout}s per operation'),
                MenuRow('Verification', value.verification),
                MenuRow('Effect scope', value.scope),
                MenuRow('Improvement guidance', value.direction or '(optional)'),
                MenuRow('Start improvement', 'Preview frozen inputs, conditions and costs before starting'),
                MenuRow('Results and history'),
            )
            selected = self.choose('Component improvement', rows,
                subtitle='Task → components → generator → exploration → verification → effect scope', key='component-workflow')
            if selected is None:
                return
            try:
                if selected == 0:
                    if await self.task_material() and not self.request.task_pack_id:
                        text = await self.read('Current task instruction')
                        if text is not None:
                            self.request = replace(self.request, instruction=text)
                elif selected == 1:
                    text = await self.read('Workspace-relative input files, separated by spaces; quote paths containing spaces')
                    if text is not None:
                        self.request = replace(value, input_paths=tuple(shlex.split(text)))
                elif selected == 2:
                    self.components()
                elif selected == 3:
                    self.choice('Candidate generator', 'generator_id', self.configuration.generators)
                elif selected == 4:
                    self.choice('Exploration mode', 'mode', self.configuration.modes)
                    await self.parameters(('width', 'depth'))
                elif selected == 5:
                    await self.parameters(('max_model_calls', 'max_executions', 'operation_timeout'))
                elif selected == 6:
                    self.choice('Verification', 'verification', self.configuration.verification)
                elif selected == 7:
                    self.choice('Effect scope', 'scope', self.configuration.scopes)
                elif selected == 8:
                    text = await self.read('Optional improvement guidance')
                    if text is not None:
                        self.request = replace(value, direction=text)
                elif selected == 9:
                    if self.external:
                        if value.scope != 'task' or value.verification != 'behavior' or value.input_paths:
                            raise ValueError('External task streams use their own inputs, execution evidence and current-task scope.')
                        benchmark_id, variant, count = self.external
                        preview = self.benchmark.benchmark_preview(BenchmarkImprovementRequest(
                            benchmark_id, variant, count, value.generator_id, value.component_ids,
                            value.mode, value.width, value.depth, value.max_model_calls, value.max_executions), value.direction)
                    else:
                        preview = self.client.workflow_preview(value)
                    subtitle = '\n'.join(f'{k}: {v}' for k, v in preview.details) + '\n\n' + preview.cost_notice
                    if self.confirm(title='Confirm component improvement', subtitle=subtitle,
                            rows=(MenuRow('Start the frozen workflow'), MenuRow('Cancel'))):
                        if await self.execute(preview, value.direction, 'benchmark' if self.external else 'workflow'):
                            return
                elif selected == 10:
                    await self.history()
            except (ValueError, TypeError, RuntimeError, OSError) as exc:
                self.report(str(exc) + '\n')

    async def task_material(self):
        materials = self.configuration.materials
        rows = [MenuRow(c.label, c.reason or c.detail) for c in materials]
        if self.benchmark is not None:
            rows.append(MenuRow('Benchmark task stream', 'Download and refine original tasks after confirmation'))
        index = self.choose('Task material', tuple(rows), key='workflow-material')
        if index is None:
            return False
        if index < len(materials):
            choice = materials[index]
            if not choice.available:
                self.report(choice.reason + '\n')
                return False
            self.external = None
            self.request = replace(self.request, task_pack_id=choice.choice_id)
            return not choice.choice_id
        if not self.benchmark.improvement_available:
            raise ValueError('No external task execution capability is registered.')
        benchmarks = self.benchmark.improvement_snapshot().benchmarks
        index = self.choose('Benchmark', tuple(MenuRow(b.label, b.description) for b in benchmarks))
        if index is None:
            return False
        benchmark = benchmarks[index]
        index = self.choose('Task environment', tuple(MenuRow(v.label,
            '; '.join(v.preflight) if not v.available else v.description) for v in benchmark.variants))
        if index is None:
            return False
        variant = benchmark.variants[index]
        if not variant.available:
            raise ValueError('; '.join(variant.preflight) or 'Task environment is unavailable.')
        text = await self.read('Task count (1–12; fixed task batches require their declared size)')
        if text is None:
            return False
        count = int(text)
        if not 1 <= count <= 12:
            raise ValueError('Task count must be 1–12.')
        self.external = (benchmark.benchmark_id, variant.variant_id, count)
        self.request = replace(self.request, task_pack_id='', input_paths=(), scope='task', verification='behavior')
        return False

    def components(self):
        while True:
            chosen = set(self.request.component_ids)
            choices = self.configuration.components
            rows = tuple(MenuRow(('[x] ' if c.component_id in chosen else '[ ] ') + c.label,
                f'{c.role} · {c.kind}' + (' · ' + c.reason if c.reason else '')) for c in choices)
            index = self.choose('Editable components', rows, subtitle='Toggle components; Back keeps the selection', key='workflow-components')
            if index is None:
                return
            component = choices[index]
            if not component.available:
                self.report(component.reason + '\n')
                continue
            chosen.symmetric_difference_update((component.component_id,))
            self.request = replace(self.request, component_ids=tuple(c.component_id for c in choices if c.component_id in chosen))

    def choice(self, title, field, choices):
        index = self.choose(title, tuple(MenuRow(c.label, c.reason or c.detail) for c in choices), key='workflow-' + field)
        if index is None:
            return
        choice = choices[index]
        if not choice.available:
            self.report(choice.reason + '\n')
            return
        self.request = replace(self.request, **{field: choice.choice_id})

    async def parameters(self, names):
        fields = tuple(p for p in self.configuration.parameters if p.name in names)
        while True:
            index = self.choose('Workflow allocation', tuple(MenuRow(p.label, str(getattr(self.request, p.name))) for p in fields), key='workflow-allocation-' + '-'.join(names))
            if index is None:
                return
            parameter = fields[index]
            text = await self.read(parameter.description + f' Range: {parameter.minimum}–{parameter.maximum}')
            if text is None:
                continue
            value = int(text) if parameter.kind == 'integer' else float(text)
            if not parameter.minimum <= value <= parameter.maximum:
                raise ValueError('value is outside the declared allocation range')
            self.request = replace(self.request, **{parameter.name: value})
