"""Immutable retained text with identical production and trial projections."""
from dataclasses import dataclass, replace

from fruitfly_agent.core.context import ContextTransform
from .targets import TargetBinding, TargetSnapshot, validate_text, state_artifact_path
from fruitfly_agent.improvement.contracts.versions import SnapshotFile, StateSnapshot


def configuration_edit(fields, bounds):
    if fields != ['parameters.initial_text'] or bounds:
        raise ValueError('retained text grants permit parameters.initial_text without numeric bounds')
    return {}


@dataclass(frozen=True)
class RetainedText:
    key: str
    text: str
    label: str
    schema: str
    max_chars: int = 16000
    reference_directory: str = ''

    adoption_roles = frozenset({'S'})

    def __post_init__(self):
        state_artifact_path(self.key)
        self.validate(self.text)

    @property
    def artifact_key(self):
        return self.key

    def snapshot(self):
        return TargetSnapshot(self.key, self.text, TargetBinding('artifact', self.key), self.schema, 'S')

    def validate(self, text):
        validate_text(text)
        if len(text) > self.max_chars:
            raise ValueError('retained document exceeds its context budget')
        if '<!-- fruitfly:' in text:
            raise ValueError('retained document cannot contain projection delimiters')

    def project(self, prompt, text):
        self.validate(text)
        start, end = f'<!-- fruitfly:{self.key}:start -->', f'<!-- fruitfly:{self.key}:end -->'
        while start in prompt:
            left = prompt.index(start)
            right = prompt.find(end, left + len(start))
            if right < 0:
                raise ValueError('incomplete retained-document projection')
            prompt = prompt[:left] + prompt[right + len(end):]
        context = (f'Current authoritative document: {self.label}. Resolve relative references against '
                   f'{self.reference_directory}. Use the body below instead of reloading its original source.\n\n'
                   if self.reference_directory else '')
        return prompt.rstrip() + f'\n\n{start}\n{context}{text}\n{end}'

    def transform(self, frame):
        prompt = self.project(frame.system_prompt, self.text)
        return None if prompt == frame.system_prompt else ContextTransform(replace(frame, system_prompt=prompt))

    def prepare_trial(self, config, text):
        return replace(config, system_prompt=self.project(config.system_prompt, text))

    def freeze(self):
        return self.freeze_text(self.text)

    def freeze_text(self, text):
        self.validate(text)
        return StateSnapshot((SnapshotFile(state_artifact_path(self.key), text),),
                             roots=(f'.fruitfly/retained/{self.key}',))


def install_retained(state, context, *, key, label, schema, initial, max_chars, reference_directory=''):
    """Install a frozen state document without editing user files or starting work."""
    from fruitfly_agent.core.context import ContextStage
    from .targets import TEXT_TARGET_PREFIX, STATE_SNAPSHOTS_COMPONENT
    reference = context.artifact_bindings.get(key)
    text = initial
    if reference is not None:
        if context.artifact_reader is None:
            raise ValueError('retained document requires an artifact reader')
        text = context.artifact_reader(reference)
        state = state.with_data_artifact({'key': key, 'id': reference, 'role': 'S',
            'media_type': 'text/plain; charset=utf-8', 'size_bytes': len(text.encode('utf-8'))})
    target = RetainedText(key, text, label, schema, max_chars, reference_directory)
    target.validate(text)
    return (state.with_component(TEXT_TARGET_PREFIX + key, target)
        .with_component(STATE_SNAPSHOTS_COMPONENT,
            (*state.components.get(STATE_SNAPSHOTS_COMPONENT, ()), target))
        .with_context_stage(ContextStage(key, 'augmentation', target, order=32)))
