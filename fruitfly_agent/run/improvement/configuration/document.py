"""Strict stage-oriented research intent; loading never runs or rewrites work."""
from copy import deepcopy
from pathlib import Path
import math
import re

from fruitfly_agent.runtime_spec.documents import DocumentReader, mapping
from fruitfly_agent.lab.improvement.api import stage_definitions, EvidenceSettings
from fruitfly_agent.improvement.contracts.plans import StageTimeouts
from fruitfly_agent.improvement.contracts.validation import identifier


class ResearchDocument:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.original = self.path.read_bytes()
        self.raw = DocumentReader().read(self.path)
        mapping(self.raw, {'research', 'baseline', 'stages', 'next'}, 'research configuration')
        self.research = mapping(self.raw.get('research'), {'id', 'title', 'output_root', 'branch'}, 'research')
        identifier(self.research.get('id'))
        identifier(self.research.get('branch', 'main'))
        self.definitions = stage_definitions()
        self.stages = mapping(self.raw.get('stages', {}), set(self.definitions), 'stages')
        self.next = mapping(self.raw.get('next', {}), {'stage'}, 'next')
        if self.next.get('stage') not in self.stages:
            raise ValueError('next.stage must name a configured independent stage')
        baseline = mapping(self.raw.get('baseline', {}), {'config', 'profile'}, 'baseline')
        for key, value in baseline.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError('baseline.' + key + ' must be nonempty text')
        for stage in self.stages:
            self.settings(stage)

    def resolve(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('research path must be a nonempty string')
        return (self.path.parent / Path(value).expanduser()).resolve()

    @property
    def root(self):
        return self.resolve(self.research.get('output_root', '.'))

    def settings(self, stage):
        if stage not in self.definitions:
            raise ValueError('unknown independent stage')
        definition = self.definitions[stage]
        common = {'inputs', 'context', 'attempt', 'publish_as', 'allowance'}
        result = mapping(self.stages.get(stage, {}), common | set(definition.controls), 'stages.' + stage)
        if result.get('attempt', 'reuse') not in {'reuse', 'fresh', 'retry-unresolved'}:
            raise ValueError('invalid stages.' + stage + '.attempt')
        if 'publish_as' in result:
            identifier(result['publish_as'])
        inputs = mapping(result.get('inputs', {}), {'harness', 'batches', 'evidence', 'assessments'}, 'stages.' + stage + '.inputs')
        def reference(value, harness=False):
            item = mapping(value, {'artifact', 'bundle', 'candidate', 'config'}, 'input reference')
            if len(item) != 1 or any(not isinstance(v, str) or not v.strip() for v in item.values()):
                raise ValueError('input reference requires one nonempty selector')
            if 'config' in item and not harness:
                raise ValueError('config references are only valid for harness inputs')
        for name, values in inputs.items():
            if name == 'harness':
                reference(values, True)
            else:
                if not isinstance(values, list):
                    raise ValueError('stage input collections must be lists')
                for item in values:
                    reference(item)
        context = result.get('context', [])
        if not isinstance(context, list):
            raise ValueError('stage context must be a list')
        for item in context:
            reference(item)
        allowance = mapping(result.get('allowance', {}), set(definition.allowance_fields), 'stages.' + stage + '.allowance')
        for name, value in allowance.items():
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value <= 0
                    or name.startswith('evidence_') and type(value) is not int):
                raise ValueError('stage allowance must contain positive finite values with integer evidence limits')
        for name in ('attempts', 'concurrency'):
            if name in result and (type(result[name]) is not int or result[name] < 1):
                raise ValueError(name + ' must be a positive integer')
        for name in ('instruction', 'direction', 'path', 'related_records'):
            if name in result and (not isinstance(result[name], str) or not result[name].strip()):
                raise ValueError(name + ' must be nonempty text')
        if 'tasks' in result:
            tasks = mapping(result['tasks'], {'file', 'inline'}, 'stage tasks')
            if len(tasks) != 1 or ('file' in tasks and (not isinstance(tasks['file'], str) or not tasks['file'].strip())) or ('inline' in tasks and not isinstance(tasks['inline'], dict)):
                raise ValueError('tasks requires exactly one file or inline document')
        if 'incremental' in result:
            EvidenceSettings.from_dict({'retention': result['incremental'], **({'delegation': result['delegation']} if 'delegation' in result else {})})
        if 'delegation' in result:
            EvidenceSettings.from_dict({'delegation': result['delegation']})
        if stage == 'propose':
            scope = mapping(result.get('optimization', {}), {'scope', 'include', 'exclude'}, 'optimization')
            if scope.get('scope', 'defaults') not in {'defaults', 'explicit'} or not isinstance(scope.get('include', {}), dict) or not isinstance(scope.get('exclude', []), list) or any(not isinstance(v, str) or not v for v in scope.get('exclude', [])):
                raise ValueError('invalid proposal optimization scope')
        if stage == 'import':
            if result.get('source') not in {'eval', 'batch'}:
                raise ValueError('import.source must be eval or batch')
            names, paths = result.get('task_names', []), result.get('evidence_paths', {})
            if not isinstance(names, list) or any(not isinstance(v, str) or not v for v in names):
                raise ValueError('import.task_names must contain task names')
            if result.get('source') != 'eval' and (names or paths):
                raise ValueError('task_names and evidence_paths require an Eval import')
            if not isinstance(paths, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', v) for k, v in paths.items()):
                raise ValueError('import.evidence_paths must map archive paths to sha256 identities')
        return result

    def experiment(self, stage):
        """Project selected intent through existing execution owner validators."""
        settings = self.settings(stage)
        allowance = settings.get('allowance', {})
        timeouts = StageTimeouts()
        execution, evaluation = {}, {'scope': 'task'}
        field = {'organize': 'organizer_seconds', 'propose': 'editor_seconds'}.get(stage)
        if field:
            execution[field] = allowance.get('seconds', getattr(timeouts, field))
        if stage in {'assess', 'compare'}:
            evaluation['evaluator_seconds'] = allowance.get('seconds', timeouts.evaluator_seconds)
        if stage == 'propose':
            execution['direction'] = settings.get('direction', '')
        if stage in {'eval', 'execute'}:
            execution['task_seconds'] = allowance.get('task_seconds', timeouts.execution_seconds)
            if 'attempts' in settings or 'concurrency' in settings:
                execution['trial'] = {k: settings[k] for k in ('attempts', 'concurrency') if k in settings}
        evidence = EvidenceSettings.from_dict({**({'delegation': settings['delegation']} if 'delegation' in settings else {}),
            **({'retention': settings['incremental']} if 'incremental' in settings else {})}).to_dict()
        for control, field in (('evidence_characters', 'max_characters'), ('evidence_responses', 'max_pages')):
            if control in allowance:
                evidence['supply'][field] = allowance[control]
        result = {'baseline': deepcopy(self.raw.get('baseline')), 'execution': execution,
            'evaluation': evaluation, 'evidence': evidence}
        if stage in {'eval', 'execute'}:
            result['tasks'] = settings.get('tasks')
        return result
