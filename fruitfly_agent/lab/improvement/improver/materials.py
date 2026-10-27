"""Strict experiment manifests referencing disjoint existing task packages."""
from dataclasses import dataclass
import json
from pathlib import Path
import unicodedata

from ..contracts.experiments import MaterialOption
from ..contracts.pipeline import canonical_json, identifier
from ..contracts.versions import content_hash
from ..tasks import read_bytes, FrozenTaskSuite
from ..tasks.models import TaskCase


@dataclass(frozen=True)
class FrozenEpisode:
    pack_id: str
    suite: FrozenTaskSuite
    holdout: tuple[TaskCase, ...]

    @property
    def evaluations(self):
        return (*self.suite.train, *self.suite.validation, *self.holdout)


@dataclass(frozen=True)
class FrozenMaterials:
    experiment_id: str
    name: str
    development: tuple[FrozenEpisode, ...]
    verification: tuple[FrozenEpisode, ...]
    source_id: str
    verification_key: str
    max_verifications: int


def _unique(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate experiment field')
        result[key] = value
    return result


def freeze(context, experiment_id, target_id):
    identifier(experiment_id)
    path = Path(context.workspace) / '.fruitfly/improvement/experiments' / experiment_id / 'experiment.json'
    data = read_bytes(Path(context.workspace), path)
    if len(data) > 16000:
        raise ValueError('experiment manifest exceeds 16 KB')
    value = json.loads(data.decode('utf-8'), object_pairs_hook=_unique)
    if (not isinstance(value, dict) or set(value) != {'id', 'name', 'development', 'verification', 'max_verifications'}
            or value['id'] != experiment_id):
        raise ValueError('invalid experiment manifest schema or identity')
    if not isinstance(value['name'], str) or not 1 <= len(value['name'].strip()) <= 120:
        raise ValueError('experiment name must contain 1–120 characters')
    if type(value['max_verifications']) is not int or not 1 <= value['max_verifications'] <= 10:
        raise ValueError('declare 1–10 independent verification uses')
    if context.tasks is None:
        raise ValueError('experiment needs a task package source')
    packs, inputs, policies = [], set(), set()
    for partition in ('development', 'verification'):
        names = value[partition]
        if not isinstance(names, list) or not 1 <= len(names) <= 8:
            raise ValueError('each experiment partition needs 1–8 task packages')
        episodes = []
        for name in names:
            identifier(name)
            if name in packs:
                raise ValueError('experiment packages must be distinct across partitions')
            packs.append(name)
            suite = context.tasks.freeze(name, target_id)
            holdout = context.tasks.holdout(name)
            if not holdout:
                raise ValueError('every experiment episode requires independent holdout')
            policies.add((suite.policy_id, suite.execution_id, suite.direction))
            episode = FrozenEpisode(name, suite, holdout)
            for case in episode.evaluations:
                key = unicodedata.normalize('NFC', case.input).strip()
                if key in inputs:
                    raise ValueError('experiment inputs overlap across packages or partitions')
                inputs.add(key)
            episodes.append(episode)
        value[partition] = tuple(episodes)
    if len(policies) != 1 or next(iter(policies))[2] != 'max':
        raise ValueError('episodes must use the same maximizing measurement implementation')
    identity = {'id': experiment_id, 'name': value['name'], 'max_verifications': value['max_verifications'],
        **{p: [(e.pack_id, e.suite.source_hash) for e in value[p]] for p in ('development', 'verification')}}
    # Count uses by semantic held-out inputs, independent of outer candidates/formatting.
    verification_key = content_hash(canonical_json({'policy': sorted(policies), 'cases': sorted(
        (unicodedata.normalize('NFC', c.input).strip(), c.expected, c.verification)
        for e in value['verification'] for c in e.evaluations)}))
    return FrozenMaterials(experiment_id, value['name'], value['development'], value['verification'],
                           content_hash(canonical_json(identity)), verification_key, value['max_verifications'])


def materials(context):
    root = Path(context.workspace) / '.fruitfly/improvement/experiments'
    if not root.exists():
        return ()
    if root.is_symlink():
        return (MaterialOption('invalid', 'Invalid experiment directory', error='experiment root cannot be a symlink'),)
    choices: list[MaterialOption] = []
    for path in sorted(root.iterdir()):
        if path.name.startswith('.') or not path.is_dir():
            continue
        if len(choices) >= 100:
            raise ValueError('experiment catalog exceeds 100 entries')
        try:
            value, error = None, None
            for document in context.components.snapshot().components:
                if document.role == 'I':
                    continue
                try:
                    value = freeze(context, path.name, document.component_id)
                    break
                except ValueError as exc:
                    error = exc
            if value is None:
                raise error or ValueError('no compatible inner component')
            choices.append(MaterialOption(path.name, value.name,
                f'{len(value.development)} development · {len(value.verification)} verification episodes'))
        except (ValueError, TypeError, OSError) as exc:
            choices.append(MaterialOption(path.name, path.name, error=str(exc)))
    return tuple(choices)
