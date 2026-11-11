"""Durable organization parts reject corrupt records and unsafe locators."""
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.improvement.contracts.organization import OrganizationPart
from fruitfly_agent.improvement.contracts.evidence import EvidenceSpan
from fruitfly_agent.run.storage.artifacts import DataArtifactStore
from fruitfly_agent.run.storage.organization_parts import OrganizationPartStore


class OrganizationPartStoreTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.artifacts = DataArtifactStore(self.root / 'artifacts')
        self.store = OrganizationPartStore(self.root / 'parts', self.artifacts)
        source = self.artifacts.put_bytes(b'observed').artifact_id
        citation = EvidenceSpan(source, 0, 8).citation_id
        self.part = OrganizationPart('Inspect source', '', 'evidence-reader', {}, {'a.txt': source},
            {'summary': 'An observation.', 'sources': [{'path': 'a.txt', 'citation_id': citation}], 'unknowns': []},
            {citation: {'path': 'a.txt', 'artifact_id': source, 'kind': 'text', 'start': 0, 'end': 8}},
            {'scope_id': 'scope', 'agent_id': 'agent', 'run_id': 'run'}, True)

    def test_save_is_idempotent_and_roundtrips_original_producer(self):
        reference = self.store.save(self.part)
        self.assertEqual(reference, self.store.save(self.part))
        reopened = OrganizationPartStore(self.root / 'parts', self.artifacts)
        self.assertEqual((reference,), reopened.entries())
        self.assertEqual(self.part, reopened.read(reference))

    def test_corrupt_and_symlink_locators_fail_discovery(self):
        reference = self.store.save(self.part)
        locator = self.root / 'parts' / (reference[7:] + '.json')
        locator.write_text('{}')
        with self.assertRaises(ValueError):
            self.store.entries()
        locator.unlink()
        locator.symlink_to(self.root / 'unowned')
        with self.assertRaises(ValueError):
            self.store.entries()

    def test_part_record_rejects_forged_source_and_unknown_fields(self):
        for change in ('citation', 'field'):
            record = self.part.to_dict()
            if change == 'citation':
                next(iter(record['citations'].values()))['end'] = 7
            else:
                record['unrecognized'] = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                OrganizationPart.from_dict(record)
