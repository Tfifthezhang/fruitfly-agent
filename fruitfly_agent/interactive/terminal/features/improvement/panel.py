"""One experiment surface with inline targets, algorithms, materials and fields."""
from dataclasses import dataclass

from fruitfly_agent.interactive.contracts.evaluation import BenchmarkImprovementRequest
from fruitfly_agent.interactive.terminal.io.input import field_prompt, parse_field_value
from fruitfly_agent.interactive.terminal.io.menu import MenuRow
from fruitfly_agent.interactive.terminal.io.text import safe_terminal_text


@dataclass(frozen=True)
class TaskChoice:
    source: str
    identity: str
    label: str
    detail: str = ''
    benchmark_id: str = ''
    direction: str = ''
    available: bool = True
    reason: str = ''


class ExperimentPanel:
    def __init__(self, *, clients, benchmark, choose, select, confirm, read, report,
                 execute, history, direction=''):
        self.clients, self.benchmark = clients, benchmark
        self.choose, self.select, self.confirm = choose, select, confirm
        self.read, self.report, self.execute, self.history = read, report, execute, history
        self.direction = direction
        self.target = self.method = self.task = self.preview = None
        self.parameters = {}
        self.budget_specs = {}
        self.problem = self.task_problem = ''
        self.targets = self.methods = self.tasks = ()
        self.has_method_catalog = False
        self.expanded = None
        self.focus = ('target',)
        self.changed = set()
        self.preview_attempted = False

    def initialize(self):
        try:
            self.targets = tuple(self.clients.targets())
            packs = tuple(p for p in self.saved_tasks() if p.available)
            if len(packs) == 1:
                self.set_task(packs[0], changed=False)
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            self.report(f'Experiment setup unavailable: {exc}\n')

    def invalidate(self, field):
        self.preview, self.problem, self.preview_attempted = None, '', False
        self.changed.add(field)

    def saved_tasks(self):
        if self.clients.search is None:
            return ()
        materials = self.clients.materials
        if materials is not None and materials.task_packs_available:
            packs = (self.clients.packs_for_target(self.target.target_id)
                if self.target is not None and self.clients.packs_for_target is not None else materials.task_packs())
            if not packs:
                return (TaskChoice('saved', '', 'Host task source', 'Validated by the host preview'),)
            return tuple(TaskChoice('saved', p.pack_id, p.name,
                f'{p.train_count} train / {p.validation_count} selection / {p.holdout_count} holdout',
                direction=p.default_direction, available=not p.error, reason=p.error) for p in packs)
        return (TaskChoice('saved', '', 'Configured task cases', 'Validated by the host preview'),)

    def set_task(self, task, *, changed=True):
        if not self.direction or self.task is not None and self.direction == self.task.direction:
            self.direction = task.direction
        self.task, self.task_problem = task, ''
        self.invalidate('task')
        if not changed:
            self.changed.discard('task')

    def set_target(self, target):
        if not target.available:
            self.report(target.reason + '\n')
            return
        if self.target != target:
            previous = self.method
            self.target = target
            options = self.clients.methods(target.role, target.target_id) if self.clients.methods is not None else None
            self.has_method_catalog = options is not None
            self.methods = tuple(options or ())
            self.method = next((m for m in self.methods if previous is not None
                and m.method_id == previous.method_id and m.available), None)
            if previous is not None and self.method is None:
                self.parameters = {p.name: self.parameters[p.name] for p in previous.parameters
                    if p.group == 'budget' and p.name in self.parameters}
                self.report('The previous algorithm is incompatible. Choose an algorithm for this target.\n')
            if self.task is not None and self.task.source == 'saved' and self.task.identity:
                self.task_problem = '' if any(p.identity == self.task.identity and p.available for p in self.saved_tasks()) else (
                    'The selected tasks are incompatible with this target. Choose tasks again.')
            self.invalidate('target')
        if self.methods and self.method is None:
            first = next((m for m in self.methods if m.available), self.methods[0])
            self.focus = ('method', first.method_id)

    def set_method(self, method):
        if not method.available:
            self.report(method.reason + '\n')
            return
        if self.method != method:
            previous_specs = ({p.name: p for p in self.method.parameters if p.group == 'budget'}
                              if self.method is not None else self.budget_specs)
            kept = {}
            for spec in method.parameters:
                previous = previous_specs.get(spec.name)
                if (spec.group == 'budget' and spec.name in self.parameters and previous is not None
                        and previous.kind == spec.kind):
                    try:
                        kept[spec.name] = parse_field_value(spec, str(self.parameters[spec.name]))
                    except ValueError:
                        pass
            if self.parameters.keys() - kept.keys():
                self.report('Parameters outside the compatible budget fields were reset for this algorithm.\n')
            self.method, self.parameters = method, kept
            self.budget_specs = {p.name: p for p in method.parameters if p.group == 'budget'}
            self.invalidate('target')

    def readiness(self):
        progress = self.clients.progress()
        if progress is not None and progress.status == 'running':
            return 'An improvement job is running; inspect Results and history or cancel it.'
        if self.target is None:
            return 'Select a target, then choose its algorithm.'
        if self.has_method_catalog and not self.methods:
            return 'No algorithm supports this target in the current runtime.'
        if self.methods and self.method is None:
            return 'Choose a compatible algorithm under Target.'
        if self.task is None:
            return 'Choose tasks.'
        if self.task_problem:
            return self.task_problem
        if self.method is not None and self.task.source not in self.method.task_sources:
            return 'The chosen algorithm does not support this task source. Change Task or Target.'
        if len(self.search_direction()) > 500:
            return 'Search guidance must contain at most 500 characters.'
        return ''

    def direction_help(self):
        if self.target is None or self.has_method_catalog and self.method is None:
            return ''
        return self.method.direction_help if self.method is not None else 'Optional guidance; task scoring remains fixed.'

    def search_direction(self):
        return self.direction.strip() if self.direction_help() else ''

    def make_preview(self):
        if self.readiness():
            raise ValueError(self.readiness())
        selection = {} if self.method is None else {'method_id': self.method.method_id, 'target_id': self.target.target_id}
        if self.parameters:
            selection['parameters'] = dict(self.parameters)
        if self.task.source == 'benchmark':
            preview = self.benchmark.benchmark_preview(BenchmarkImprovementRequest(
                self.task.benchmark_id, self.task.identity, **selection), self.search_direction())
        else:
            preview = self.clients.search.improvement_preview(pack_id=self.task.identity or None,
                direction=self.search_direction(), **selection)
        if (preview.role, preview.target) != (self.target.role, self.target.target_id):
            raise ValueError('preview differs from the selected target or role')
        if self.method is not None and preview.algorithm != self.method.method_id:
            raise ValueError('preview differs from the selected improvement algorithm')
        return preview

    def parameter_values(self):
        return {**({p.name: p.value for p in self.method.parameters} if self.method else {}), **self.parameters}

    def budget_text(self):
        values = self.parameter_values()
        specs = tuple(p for p in self.method.parameters if p.group == 'budget') if self.method else ()
        if specs:
            return ' · '.join(f'{p.label}: {values.get(p.name)}' for p in specs[:2])
        details = dict(self.preview.details) if self.preview else {}
        return (details.get('Maximum model calls', '?') + ' model calls · '
            + details.get('Maximum metric calls', details.get('Maximum task trials', '?')) + ' task trials')

    def evaluation_details(self):
        details = dict(self.method.requirements) if self.method else {}
        if self.target is not None:
            details['Target ID'] = self.target.target_id
        if self.preview:
            details.update(self.preview.details)
        return details

    def layout(self):
        rows, actions = [], []
        values = self.parameter_values()

        def add(action, label, detail='', **style):
            actions.append(action)
            rows.append(MenuRow(label, detail, **style))

        def field(spec, owner):
            add(('parameter', owner, spec.name), f'{spec.label} · {values.get(spec.name)}', spec.description,
                depth=1, section=owner.capitalize(), changed=spec.name in self.parameters)

        arrow = lambda key: ' ▴' if self.expanded == key else ' ▾'
        algorithm = (self.method.label if self.method else 'Choose algorithm' if self.methods else
                     'No compatible algorithm' if self.has_method_catalog else 'Host algorithm' if self.target else '')
        add(('target',), 'Target · ' + (self.target.label if self.target else 'Choose target')
            + (' · ' + algorithm if algorithm else '') + arrow('target'), changed='target' in self.changed)
        if self.expanded == 'target':
            for target in self.targets:
                chosen = self.target == target
                add(('object', target.role, target.target_id), target.label, target.reason if not target.available else '',
                    marker='●' if chosen else '○', depth=1, section='Targets · ' + target.role,
                    state='unavailable' if not target.available else 'selected' if chosen else '')
            for method in self.methods:
                chosen = self.method == method
                add(('method', method.method_id), method.label + (' · suggested' if method.default and not chosen else ''),
                    method.description + ('' if method.available else ' · Unavailable · ' + method.reason),
                    marker='●' if chosen else '○', depth=1, section='Algorithms',
                    state='unavailable' if not method.available else 'selected' if chosen else '',
                    references=tuple((label, path) for label, path in (
                        ('Implementation', method.implementation_path), ('Guide', method.documentation_path)) if path))
            if self.method is not None:
                if self.method.configuration_path:
                    add(('info', 'Configuration'), 'Configuration location',
                        f'profiles.{self.method.configuration_profile}.mechanisms · id: {self.method.method_id} · parameters',
                        depth=1, section='Algorithms',
                        references=(('Configuration', self.method.configuration_path),))
            if self.direction_help():
                add(('guidance',), 'Search guidance · ' + (self.direction or '(optional; not set)'),
                    self.direction_help(), depth=1, section='Target', changed='guidance' in self.changed)
        add(('task',), 'Task · ' + (self.task.label if self.task else 'Choose tasks') + arrow('task'),
            self.task.detail if self.task else '', changed='task' in self.changed)
        if self.expanded == 'task':
            for task in self.tasks:
                reason = task.reason
                if self.method is not None and task.source not in self.method.task_sources:
                    reason = 'The selected algorithm does not support this task source'
                chosen = self.task == task
                add(('tasks', task.source, task.benchmark_id, task.identity), task.label,
                    'Unavailable · ' + reason if reason else task.detail, marker='●' if chosen else '○', depth=1,
                    section='Saved tasks' if task.source == 'saved' else 'Benchmark tasks',
                    state='unavailable' if reason or not task.available else 'selected' if chosen else '')
            if self.method is not None:
                for spec in self.method.parameters:
                    if spec.group == 'materials':
                        field(spec, 'task')
        add(('budget',), 'Budget · ' + self.budget_text() + arrow('budget'), changed='budget' in self.changed)
        if self.expanded == 'budget':
            specs = tuple(p for p in self.method.parameters if p.group == 'budget') if self.method else ()
            for spec in specs:
                field(spec, 'budget')
            if not specs:
                add(('info', 'Budget'), 'Host-controlled budget', 'Choose an algorithm for editable budget fields.', depth=1, section='Budget')
        details = self.evaluation_details()
        evaluation = details.get('Evaluation policy', details.get('Objective policy', 'Declared by the task source'))
        acceptance = details.get('Independent confirmation', details.get('Acceptance', 'Review a complete preview'))
        add(('evaluation',), 'Evaluation · ' + evaluation + arrow('evaluation'), acceptance)
        if self.expanded == 'evaluation':
            for key, value in details.items():
                add(('detail', key, value), key, value, depth=1, section='Evaluation and acceptance')
        for key, label in (('start', 'Start improvement'), ('history', 'Results and history'), ('return', 'Return to chat')):
            add((key,), label)
        return tuple(rows), actions

    async def run(self):
        self.initialize()
        while True:
            problem = self.readiness()
            if not problem and self.preview is None and not self.preview_attempted:
                self.preview_attempted = True
                try:
                    self.preview, self.problem = self.make_preview(), ''
                except (OSError, RuntimeError, ValueError, TypeError) as exc:
                    self.problem = str(exc)
                    self.report(f'Experiment preview unavailable: {safe_terminal_text(str(exc))}\n')
            rows, actions = self.layout()
            choice = self.select('Improvement · Experiment', rows,
                subtitle=safe_terminal_text(problem or self.problem or 'Ready. Review settings, then start one experiment.'),
                selected=actions.index(self.focus) if self.focus in actions else 0)
            if choice is None:
                if self.expanded is not None:
                    self.focus, self.expanded = (self.expanded,), None
                    continue
                return
            action = actions[choice]
            self.focus = action
            if action[0] == 'return':
                return
            try:
                if action[0] in {'target', 'task', 'budget', 'evaluation'}:
                    self.expanded = None if self.expanded == action[0] else action[0]
                    if self.expanded == 'task':
                        self.tasks = self.task_choices()
                elif action[0] == 'object':
                    self.set_target(next(t for t in self.targets if (t.role, t.target_id) == action[1:]))
                elif action[0] == 'method':
                    self.set_method(next(m for m in self.methods if m.method_id == action[1]))
                elif action[0] == 'tasks':
                    task = next(t for t in self.tasks if (t.source, t.benchmark_id, t.identity) == action[1:])
                    if not task.available or self.method is not None and task.source not in self.method.task_sources:
                        self.report((task.reason or 'The selected algorithm does not support this task source') + '\n')
                    else:
                        self.set_task(task)
                elif action[0] == 'parameter':
                    spec = next(p for p in self.method.parameters if p.name == action[2])
                    value = await self.read(field_prompt(spec, self.parameter_values().get(spec.name)))
                    if value is not None and value.strip() and value.strip() != '/cancel':
                        try:
                            self.parameters[spec.name] = parse_field_value(spec, value)
                            self.invalidate(action[1])
                        except ValueError as exc:
                            self.report(f'Invalid parameter: {exc}\n')
                elif action[0] == 'guidance':
                    await self.edit_guidance()
                elif action[0] == 'detail':
                    self.choose(action[1], (), subtitle=safe_terminal_text(action[2]))
                elif action[0] == 'history':
                    await self.history()
                elif action[0] == 'start':
                    self.preview = self.make_preview()
                    if not self.confirm(title='Confirm improvement', subtitle=self.confirmation_text(),
                        rows=(MenuRow('Start improvement'), MenuRow('Cancel'))):
                        self.report('Improvement cancelled; no task download or model calls started.\n')
                        continue
                    if await self.execute(self.preview, self.search_direction(), self.task.source):
                        return
            except (OSError, RuntimeError, ValueError, TypeError) as exc:
                self.problem = str(exc)
                self.report(f'Cannot run improvement: {safe_terminal_text(str(exc))}\n')

    def task_choices(self):
        try:
            choices = list(self.saved_tasks())
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            self.report(f'Saved tasks unavailable: {exc}\n')
            choices = [TaskChoice('saved', '', 'Task packages', available=False, reason=str(exc))]
        if self.benchmark is not None:
            if not self.benchmark.improvement_available:
                choices.append(TaskChoice('benchmark', '', 'Benchmark tasks', available=False,
                    reason='no executable search and verification binding'))
            else:
                try:
                    snapshot = self.benchmark.improvement_snapshot()
                    if not snapshot.benchmarks:
                        self.report('No benchmark task sources are available.\n')
                    for benchmark in snapshot.benchmarks:
                        if not benchmark.variants:
                            choices.append(TaskChoice('benchmark', '', benchmark.label, available=False, reason='No task sets are available'))
                        for variant in benchmark.variants:
                            choices.append(TaskChoice('benchmark', variant.variant_id,
                                benchmark.label + ' / ' + variant.label, variant.description, benchmark.benchmark_id,
                                'Improve completion of the frozen original benchmark tasks.', variant.available, '; '.join(variant.preflight)))
                except (OSError, RuntimeError, ValueError, TypeError) as exc:
                    self.report(f'Benchmark catalog unavailable: {exc}\n')
                    choices.append(TaskChoice('benchmark', '', 'Task catalog', available=False, reason=str(exc)))
        return tuple(choices)

    async def edit_guidance(self):
        value = await self.read(f'Search guidance (optional)\n{self.direction_help()}\nCurrent: {self.direction or "(not set)"}\n'
            'Blank keeps current; /clear removes it; Esc or /cancel returns.')
        if value is None or not value.strip() or value.strip() == '/cancel':
            return
        text = '' if value.strip() == '/clear' else value.strip()
        if len(text) > 500:
            raise ValueError('search guidance must contain at most 500 characters')
        self.direction = text
        self.invalidate('guidance')

    def confirmation_text(self):
        return safe_terminal_text(f'Role: {self.target.role} · Target: {self.target.label}\nTask: {self.task.label} · {self.task.detail}\n'
            + (f'Search guidance: {self.search_direction() or "(not set)"}\n' if self.direction_help() else '')
            + f'Algorithm: {self.preview.label}\nBudget: {self.budget_text()}\n{self.preview.cost_notice}\n'
            + '\n'.join(f'{key}: {value}' for key, value in self.preview.details))
