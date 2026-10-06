"""Map saved selections and latest candidates to opaque startup choices."""
from dataclasses import replace
import hashlib
import json

from fruitfly_agent.interactive.configuration import StartupVersion
from fruitfly_agent.lab.base_prompt import DEFAULT_PROMPT_ID


class RunStartupVersions:
    def __init__(self, factory):
        self.factory = factory
        self._receipts = {}

    def versions(self, snapshot):
        factory = self.factory
        profile = factory.configuration._draft.select(snapshot.selected_profile)
        scope = (str(factory.selection.config_path.resolve()), profile.profile_id)
        latest = {}
        for record in factory.candidate_store.list():
            if (record.config_path, record.profile_id) == scope:
                latest.setdefault(record.target, record)
        records = tuple(latest.values())
        slots = {slot for item in factory.catalog.resolve(profile.mechanisms)
                 for slot in item.definition.artifact_slots}
        bindings = {'base_prompt': ('prompt', '')}
        bindings.update({key: ('artifact', key) for key in profile.artifact_bindings if key in slots})
        for record in records:
            if record.binding_kind == 'prompt' or record.binding_key in slots:
                bindings[record.target] = (record.binding_kind, record.binding_key)
        result = []
        for target, (kind, key) in bindings.items():
            if kind == 'artifact' and key in factory.data_artifact_bindings:
                continue  # Constructor-pinned bindings are not selectable versions.
            ref = profile.prompt if kind == 'prompt' else profile.artifact_bindings.get(key)
            pending = next((r for r in records if r.target == target
                            and r.status in {'proposed', 'reviewed', 'deferred', 'selected_for_next_session', 'adopted'}
                            and r.artifact_id != ref), None)
            # Keep the ordinary startup path as short as before until there is a version choice.
            if not pending and (ref == DEFAULT_PROMPT_ID if kind == 'prompt' else ref is None):
                continue
            choices = [('Current selected version', 'current', None, True),
                       ('Object default version', 'default', None, False)]
            if pending:
                accepted = pending.status == 'adopted'
                choices.append(('Latest accepted improvement' if accepted else 'Latest improvement (review required)',
                                'accepted' if accepted else 'candidate', pending.candidate_id, False))
                if pending.task_pack_name or pending.task_pack_id:
                    label, action, identity, current = choices[-1]
                    choices[-1] = (f'{pending.task_pack_name or pending.task_pack_id} · {label}', action, identity, current)
            for label, action, candidate_id, current in choices:
                data = (scope, profile.to_dict(), target, kind, key, action, candidate_id)
                token = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
                self._receipts[token] = (profile, kind, key, action, candidate_id)
                detail = f'{snapshot.config_path} · {profile.profile_id} · {target}'
                text = ''
                if action in {'candidate', 'accepted'}:
                    try:
                        text = factory.artifact_store.read_text(pending.artifact_id)
                    except (OSError, ValueError):
                        continue
                    detail += (f'\nBaseline selection: {pending.seed_score}; candidate: {pending.validation_score}'
                               '\nIndependent verification: not provided by search')
                result.append(StartupVersion(token, target, label, detail, current, text))
        return tuple(result)

    async def prepare(self, manifest, tokens, *, remember=()):
        factory = self.factory
        original = factory.selection.profile
        profile = factory._active_profile or original
        persistent = original
        candidates = []
        seen = set()
        for token in tokens:
            if token not in self._receipts:
                raise ValueError('startup version selection expired')
            expected, kind, key, action, candidate_id = self._receipts[token]
            if expected != original or factory._resolve().profile != original:
                raise ValueError('configuration changed before version selection')
            if (kind, key) in seen:
                raise ValueError('duplicate startup target selection')
            seen.add((kind, key))
            record = None
            if action == 'candidate':
                record, _ = factory.candidate_profile(manifest, candidate_id)
                ref = record.artifact_id
                candidates.append((record, token in remember))
            elif action == 'accepted':
                record = factory.candidate_store.read(candidate_id)
                factory._check_candidate_scope(record)
                if record.status != 'adopted' or (record.binding_kind, record.binding_key) != (kind, key):
                    raise ValueError('accepted startup version changed')
                target = factory._current_targets.get(record.target)
                if target is None or (target.snapshot().binding.kind, target.snapshot().binding.key) != (kind, key):
                    raise ValueError('accepted version target binding changed')
                target.validate(factory.artifact_store.read_text(record.artifact_id))
                ref = record.artifact_id
            elif action == 'default':
                ref = DEFAULT_PROMPT_ID if kind == 'prompt' else None
            else:
                ref = original.prompt if kind == 'prompt' else original.artifact_bindings.get(key)
            def apply(value):
                if kind == 'prompt':
                    return replace(value, prompt=ref)
                bindings = dict(value.artifact_bindings)
                if ref is None:
                    bindings.pop(key, None)
                else:
                    bindings[key] = ref
                return replace(value, artifact_bindings=bindings)
            profile = apply(profile)
            if token in remember:
                persistent = apply(persistent)
        handle = await factory.open(resume=False, session_path=factory.new_session_path(), profile_override=profile)
        activate_original = handle.activate_callback
        def activate():
            if factory._resolve().profile != original or factory.configuration.snapshot().changed:
                raise ValueError('configuration changed while preparing startup version')
            for record, saved in candidates:
                factory.candidate_profile(manifest, record.candidate_id)
            if remember:
                staged = []
                for record, saved in candidates:
                    if saved:
                        factory.candidate_store.update(record.candidate_id, status='selected_for_next_session')
                        staged.append(record)
                factory.configuration._replace_profile(persistent)
                try:
                    factory.configuration.save()
                except BaseException:
                    factory.configuration.reset()
                    for record in staged:
                        factory.candidate_store.update(record.candidate_id, status=record.status)
                    raise
                factory.reload_configuration()
            activate_original()
            for record, saved in candidates:
                if saved:
                    factory.candidate_store.update(record.candidate_id, status='adopted',
                                                   activated_manifest_digest=handle.manifest['digest'])
        handle.activate_callback = activate
        return handle
