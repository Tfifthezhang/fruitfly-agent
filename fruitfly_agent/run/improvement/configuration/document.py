"""Read user intent separately from generated observations; never run a stage."""
from copy import deepcopy
from pathlib import Path
import re
import yaml

from fruitfly_agent.runtime_spec.documents import DocumentReader, mapping
from fruitfly_agent.run.configuration.persistence import write_bytes

STAGES = ('eval', 'import', 'organize', 'assess', 'propose', 'execute', 'compare')
BEGIN = '# BEGIN GENERATED RESEARCH OBSERVATIONS\n'
END = '# END GENERATED RESEARCH OBSERVATIONS\n'


class ResearchDocument:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.original = self.path.read_bytes()
        self.raw = DocumentReader().read(self.path)
        mapping(self.raw, {'research', 'baseline', 'roles', 'overrides', 'optimization',
            'stages', 'evidence', 'next', 'observed'}, 'research configuration')
        self.research = mapping(self.raw.get('research'), {'id', 'title', 'output_root', 'branch', 'history_entries'}, 'research')
        from fruitfly_agent.improvement.contracts.validation import identifier
        identifier(self.research.get('id'))
        identifier(self.research.get('branch', 'main'))
        if type(self.research.get('history_entries', 10)) is not int or self.research.get('history_entries', 10) < 1:
            raise ValueError('research.history_entries must be a positive integer')
        self.stages = mapping(self.raw.get('stages', {}), set(STAGES), 'stages')
        self.next = mapping(self.raw.get('next', {}), {'stage', 'inputs', 'context', 'attempt', 'publish_as'}, 'next')
        if self.next.get('stage') not in STAGES:
            raise ValueError('next.stage must name one independent stage')
        if self.next.get('attempt', 'reuse') not in {'reuse', 'fresh', 'retry-unresolved'}:
            raise ValueError('invalid next.attempt')
        mapping(self.raw.get('roles', {}), {'executor', 'organizer', 'assessor', 'editor'}, 'roles')

    def resolve(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('research path must be a nonempty string')
        return (self.path.parent / Path(value).expanduser()).resolve()

    @property
    def root(self):
        return self.resolve(self.research.get('output_root', '.'))

    def settings(self, stage):
        if stage not in STAGES:
            raise ValueError('unknown independent stage')
        allowed = {
            'eval': {'tasks', 'task_seconds'},
            'import': {'source', 'path', 'related_records'},
            'organize': {'timeout_seconds', 'instruction'},
            'assess': {'timeout_seconds'},
            'propose': {'timeout_seconds', 'generator', 'direction'},
            'execute': {'tasks', 'attempts', 'concurrency', 'task_seconds'},
            'compare': {'timeout_seconds'},
        }
        return mapping(self.stages.get(stage, {}), allowed[stage], 'stages.' + stage)

    def experiment(self, stage):
        """Project into existing owner validators, without a second component grammar."""
        settings = self.settings(stage)
        execution, evaluation = {}, {'scope': 'task'}
        if stage in {'organize', 'propose'}:
            execution[{'organize': 'organizer_seconds', 'propose': 'editor_seconds'}[stage]] = settings.get('timeout_seconds', 1200)
        if stage in {'assess', 'compare'}:
            evaluation['evaluator_seconds'] = settings.get('timeout_seconds', 1200)
        if stage == 'propose':
            execution.update(generator=settings.get('generator', 'agent-editor-v1'), direction=settings.get('direction', ''))
        if stage in {'eval', 'execute'}:
            execution['task_seconds'] = settings.get('task_seconds', 3600)
            if 'attempts' in settings or 'concurrency' in settings:
                execution['trial'] = {k: settings[k] for k in ('attempts', 'concurrency') if k in settings}
        result = {'baseline': deepcopy(self.raw.get('baseline')), 'execution': execution,
            'evaluation': evaluation, 'evidence': deepcopy(self.raw.get('evidence', {}))}
        if stage in {'eval', 'execute'}:
            result['tasks'] = settings.get('tasks')
        return result

    def update_observed(self, observed):
        """Preserve authored bytes and refuse to overwrite concurrent user edits."""
        from contextlib import contextmanager
        import fcntl
        lock = self.path.with_name('.' + self.path.name + '.lock')
        with lock.open('a+') as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            if self.path.read_bytes() != self.original:
                return False
            text = self.original.decode()
            if BEGIN in text:
                before, tail = text.split(BEGIN, 1)
                if END not in tail:
                    raise ValueError('unfinished generated observation block')
                _, after = tail.split(END, 1)
                text = before + after
            elif 'observed' in self.raw:
                node = yaml.compose(text)
                for index, (key, value) in enumerate(node.value):
                    if key.value == 'observed':
                        end = node.value[index + 1][0].start_mark.index if index + 1 < len(node.value) else len(text)
                        text = text[:key.start_mark.index] + text[end:]
                        break
            text = text.rstrip() + '\n\n' + BEGIN + yaml.safe_dump({'observed': observed}, sort_keys=False, allow_unicode=True) + END
            write_bytes(self.path, text.encode())
            self.original = text.encode()
            return True
