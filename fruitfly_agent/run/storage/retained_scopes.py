"""Route owner-declared retained libraries to user or workspace checkpoints."""
from copy import deepcopy
import json
from pathlib import Path

from fruitfly_agent.improvement.contracts.versions import StateSnapshot, SnapshotFile, canonical_json, content_hash


class RetainedArtifacts:
    def __init__(self, user, workspace):
        self.user, self.workspace = user, workspace

    def put_text(self, text):
        return self.user.put_text(text)

    def read_text(self, reference):
        path = self.user.root / reference.removeprefix('sha256:')
        return (self.user if path.exists() or path.is_symlink() else self.workspace).read_text(reference)


class RetainedScopes:
    def __init__(self, workspace, user, user_libraries):
        self.workspace, self.user = workspace, user
        self.user_libraries = frozenset(user_libraries)
        self.artifacts = RetainedArtifacts(user.artifacts, workspace.artifacts)

    def store_for(self, key):
        return self.user if key in self.user_libraries else self.workspace

    def read(self):
        value = self.user.read()
        value['libraries'] = {**{k: v for k, v in self.workspace.read()['libraries'].items()
            if k not in self.user_libraries}, **{k: v for k, v in value['libraries'].items()
                if k in self.user_libraries}}
        return value

    def library(self, key):
        return self.store_for(key).library(key)

    def observe(self, evidence):
        return self.user.observe(evidence)

    def maintenance_lease(self):
        return self.user.maintenance_lease()

    def begin(self, *args, **kwargs):
        return self.user.begin(*args, **kwargs)

    def finish(self, *args, **kwargs):
        return self.user.finish(*args, **kwargs)

    def read_journal(self, operation):
        return self.user.read_journal(operation)

    def record_journal(self, identity, journal):
        return self.user.record_journal(identity, journal)

    def resume(self, identity):
        return self.user.resume(identity)

    def allow_retry(self, identity):
        return self.user.allow_retry(identity)


    def end_legacy_operation(self, identity):
        return self.user.end_legacy_operation(identity)

    def discard(self, identity):
        return self.user.discard(identity)

    def publish(self, identity):
        return self.user.publish(identity)

    def review(self, identity, action):
        return self.user.review(identity, action)

    def review_with_activation(self, identity, action, activate):
        return self.user.review_with_activation(identity, action, activate)

    def adopt_with_activation(self, documents, expected, activate):
        # Lock in a fixed order. Nested store transactions restore each checkpoint
        # if a later publication or the activation callback fails.
        groups = [(store, {k: v for k, v in documents.items() if self.store_for(k) is store})
                  for store in (self.user, self.workspace)]
        def publish(index):
            if index == len(groups):
                return activate()
            store, values = groups[index]
            parent = {k: v for k, v in expected.items() if self.store_for(k) is store}
            parent.update({k: v for k, v in store.read()['libraries'].items() if self.store_for(k) is not store})
            return store.adopt_with_activation(values, parent, lambda: publish(index + 1))
        return publish(0)

    def import_workspace(self, path, *, validators):
        from .artifacts import DataArtifactStore
        from .retained_state import RetainedStateStore
        root = Path(path).expanduser().resolve() / '.fruitfly'
        sources = [RetainedStateStore(p.parent, DataArtifactStore(root / 'artifacts'))
                   for p in sorted((root / 'retained').glob('*/state.json'))
                   if p.parent != self.user.root]
        if not sources:
            raise ValueError('workspace has no retained checkpoints')
        # Validate every input and prepare immutable bytes before publishing a
        # single merged checkpoint. Source files remain available for inspection.
        captured = []
        for source in sources:
            state = source.read()
            for key, reference in state['libraries'].items():
                if key in self.user_libraries:
                    if key not in validators:
                        raise ValueError('enable the memory owner before importing')
                    validators[key](json.loads(source.artifacts.read_text(reference)))
            for row in state['pending'].values():
                if row['key'] in self.user_libraries:
                    validators[row['key']](json.loads(source.artifacts.read_text(row['artifact'])))
            references = {row['artifact'] for row in state['evidence']}
            references.update(state['libraries'].values())
            references.update(row['artifact'] for row in state['pending'].values())
            references.update(row['parent'] for row in state['pending'].values() if row['parent'])
            for reference in references:
                self.user.artifacts.put_text(source.artifacts.read_text(reference))
            captured.append(state)
        with self.user.maintenance_lease() as acquired:
            if not acquired:
                raise ValueError('maintenance is still running')
            def merge(value):
                if any('journal' in row and row['status'] not in {'completed', 'discarded'} for row in value['operations'].values()):
                    raise ValueError('resolve current maintenance before importing')
                for state in captured:
                    source_id = content_hash(canonical_json(state))
                    receipt = 'import-' + source_id.removeprefix('sha256:')
                    if receipt in value['operations']:
                        continue
                    for key, reference in state['libraries'].items():
                        if key not in self.user_libraries:
                            continue
                        before = json.loads(self.user.artifacts.read_text(value['libraries'][key])) if key in value['libraries'] else []
                        entries = {entry['id']: entry for entry in before}
                        for entry in json.loads(self.user.artifacts.read_text(reference)):
                            if entry['id'] in entries and entries[entry['id']] != entry:
                                raise ValueError('imported memory identity conflicts')
                            entries[entry['id']] = entry
                        merged = validators[key](list(entries.values()))
                        value['libraries'][key] = self.user.artifacts.put_text(canonical_json(merged)).artifact_id
                    known = {row['identity']: row for row in value['evidence']}
                    processed: list[dict] = []
                    remaining: list[dict] = []
                    for index, row in enumerate(state['evidence']):
                        if row['identity'] in known:
                            if any(known[row['identity']][key] != item for key, item in row.items() if key != 'completed'):
                                raise ValueError('imported evidence identity conflicts')
                            known[row['identity']]['completed'] |= row['completed']
                            continue
                        known[row['identity']] = row
                        (processed if index < state['processed'] else remaining).append(deepcopy(row))
                    cursor = value['processed']
                    value['evidence'][cursor:cursor] = processed
                    value['processed'] += len(processed)
                    value['evidence'].extend(remaining)
                    for identity, row in state['operations'].items():
                        if 'journal' in row:
                            raise ValueError('import of active-format maintenance journals requires a frozen state transfer')
                        if identity in value['operations'] and any(value['operations'][identity][key] != row[key]
                                for key in ('operation', 'request_id')):
                            raise ValueError('imported operation identity conflicts')
                        value['operations'].setdefault(identity, deepcopy(row))
                    for identity, row in state['pending'].items():
                        if row['key'] in self.user_libraries:
                            if identity in value['pending'] and any(value['pending'][identity][key] != item
                                    for key, item in row.items() if key != 'status'):
                                raise ValueError('imported pending update conflicts')
                            value['pending'].setdefault(identity, deepcopy(row))
                    value['operations'][receipt] = {'operation': 'import', 'request_id': source_id, 'status': 'completed'}
                return 'imported'
            return self.user.mutate(merge)

    def freeze(self):
        files: dict[str, SnapshotFile] = {}
        roots: list[str] = []
        for store in (self.workspace, self.user):
            snapshot = store.freeze()
            for file in snapshot.files:
                if file.path in files and files[file.path] != file:
                    raise ValueError('retained snapshots conflict')
                files[file.path] = file
            roots.extend(snapshot.roots)
        return StateSnapshot(tuple(files.values()), roots=tuple(dict.fromkeys(roots)))
