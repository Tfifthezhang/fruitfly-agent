"""Native task-pack collections preserve their declared private partitions."""
import unicodedata

from fruitfly_agent.improvement.contracts.task_sets import CollectionBinding, ScoreSpec, TaskEntry, TaskSetSourceDefinition
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.versions import content_hash
from fruitfly_agent.improvement.contracts.experiments import ExecutionPorts
from ..execution.file_runner import FileTaskRunner
from ..assessment.verification import CaseMeasurements


def freeze(spec, context):
    if set(spec) - {'id', 'source', 'pack', 'model_calls', 'objective'}:
        raise ValueError('unknown file collection fields')
    pack = spec.get('pack')
    if not isinstance(pack, str) or not pack:
        raise ValueError('a file collection needs an installed task pack')
    for component in context.component_ids:
        suite = context.tasks.freeze(pack, component)
    holdout = context.tasks.holdout(pack)
    groups = context.tasks.case_groups(pack)
    score = spec.get('objective', {})
    if not isinstance(score, dict) or set(score) - {'minimum', 'maximum'}:
        raise ValueError('file objective accepts minimum and maximum')
    objective = ScoreSpec(suite.policy_id, direction=suite.direction, **score)
    entries, cases = [], {}
    for partition, material in (('development', suite.train), ('selection', suite.validation), ('confirmation', holdout)):
        for case in material:
            origin = 'native-text:' + content_hash(unicodedata.normalize('NFC', case.input).strip())
            key = spec['id'] + '-' + content_hash(origin)[7:31]
            task = TaskMaterial(key, case.input, environment_id='file-workspace-v1', origin='task-pack:' + pack)
            entries.append(TaskEntry(key, spec['id'], suite.source_hash, spec['id'], task, objective, origin,
                group_id=groups.get(case.case_id) or origin, partition=partition, model_limit=spec.get('model_calls', 8)))
            cases[key] = case

    def current_source():
        return context.tasks.source_hash(pack)

    def build(leaf):
        runner = FileTaskRunner(leaf.config, leaf.components, leaf.artifacts, leaf.services,
            tool_names={tool.name for tool in leaf.config.tools})
        return ExecutionPorts(runner, CaseMeasurements(suite.evaluation_policy, cases), retain_experience=False)

    return CollectionBinding(tuple(entries), build, current_source, suite.source_hash, FileTaskRunner.capabilities)


def definition():
    return TaskSetSourceDefinition('files', 'file-pack-collection-v1', freeze)
