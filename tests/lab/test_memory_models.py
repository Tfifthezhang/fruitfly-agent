"""Memory shape, immutable evidence and explicit update semantics."""
from copy import deepcopy
import unittest
from fruitfly_agent.lab.context_manager.augmentation.memory.methods.file_memory.models import MemoryEvidence
from fruitfly_agent.lab.context_manager.augmentation.memory.methods.file_memory.validation import validate_memories, apply_changes
from fruitfly_agent.lab.catalog.adapters.collections import parse_documents
from tests.support.retained import memory


class MemoryModelsTests(unittest.TestCase):
    def test_all_kinds_and_project_scope_have_one_strict_shape(self):
        for kind in ('profile', 'preference', 'feedback', 'project', 'reference'):
            value = memory(); value['kind'] = kind
            self.assertEqual([value], validate_memories([value]))
        for field, value in (('scope', 'global'), ('kind', 'unknown'), ('body', ''), ('extra', True)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_memories([{**memory(), field: value}])

    def test_unknown_sources_duplicates_and_cycles_fail(self):
        for values in ([memory(), memory()], [{**memory(), 'provenance': {}}],
                       [{**memory(), 'supersedes': ['memory-missing']}],
                       [{**memory(), 'supersedes': ['memory-editor']}]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_memories(values)

    def test_empty_changes_preserve_all_existing_notes_and_invalid_changes_do_not_delete(self):
        entries = [memory(), memory('memory-other')]
        self.assertEqual(entries, apply_changes(entries, [], evidence=(), observed_at='now'))
        with self.assertRaises(ValueError):
            apply_changes(entries, [{}], evidence=(), observed_at='now')
        self.assertEqual('active', entries[0]['status'])

    def test_new_memory_uses_only_host_attributed_evidence(self):
        evidence = MemoryEvidence('session-b', 'session:2', 'Prefer B.', True)
        change = {'operation': 'add', 'entry': {k: v for k, v in memory(body='Prefer B.').items()
            if k in {'kind', 'subject', 'description', 'body', 'applicability', 'supersedes'}},
            'evidence_ids': [evidence.identity]}
        result = apply_changes([], [change], evidence=(evidence,), observed_at='now')
        self.assertEqual(['session:2'], result[0]['provenance']['message_ids'])
        change['evidence_ids'] = ['fabricated']
        with self.assertRaises(ValueError):
            apply_changes([], [change], evidence=(evidence,), observed_at='now')

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_documents('[{"id":"first","id":"second"}]')

    def test_dense_acyclic_replacements_are_validated_without_revisiting_every_path(self):
        entries = []
        for index in range(60):
            entry = memory('memory-' + str(index))
            entry['supersedes'] = [previous['id'] for previous in entries]
            entries.append(entry)
        self.assertEqual(60, len(validate_memories(entries)))
