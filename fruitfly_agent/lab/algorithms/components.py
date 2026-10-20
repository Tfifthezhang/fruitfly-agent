"""Compose object-owned text adapters into one executable candidate."""
from .targets import TargetBinding, TargetSnapshot, canonical_json, expand_target


class ComponentTarget:
    """Independent H/S/I bindings with declared leaf roles; no activation authority."""
    adoption_roles = frozenset({'H', 'S', 'I'})

    def __init__(self, target_id, label, targets):
        self.target_id, self.label = target_id, label
        self.targets = tuple(targets)
        snapshots = tuple(target.snapshot() for target in self.targets)
        if not snapshots:
            raise ValueError('a component target cannot be empty')
        self.value = TargetSnapshot(target_id,
            canonical_json({p.target_id: p.text for p in snapshots}),
            TargetBinding('components'), 'instruction-components-v1', snapshots[0].role, snapshots)
        self.requires_runtime_trials = any(getattr(t, 'requires_runtime_trials', False) for t in self.targets)

    def snapshot(self):
        return self.value

    def validate(self, text):
        for target, (_, value) in zip(self.targets, expand_target(self.value, text)):
            if value != target.snapshot().text:
                target.validate(value)

    def prepare_trial(self, config, text):
        self.validate(text)
        for target, (_, value) in zip(self.targets, expand_target(self.value, text)):
            if value != target.snapshot().text:
                config = target.prepare_trial(config, value)
        return config
