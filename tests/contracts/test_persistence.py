"""Fixed wire examples, independent of current serialization constructors."""
import json
import tempfile
import unittest
from pathlib import Path
from dataclasses import fields
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.env.types import ExecOptions, ExecResult, FileInfo
from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.run.assembly import RuntimeManifest
from eval.contracts import EvaluationRequest
from tests.support.evaluation import request_payload


# Fixed JSONL must remain readable without rewriting it first.
SESSION_V1 = '{"id":1,"parentId":null,"type":"message","timestamp":0.0,"message":{"role":"user","content":"hello","timestamp":0.0}}\n'
REQUEST_V1 = '''{
  "schema_version": 1, "mode": "current_setup",
  "runtime": {"manifest": {"digest": "sha256:test", "components": []},
    "config_path": "/tmp/config.yaml", "profile": "test", "working_directory": "/tmp/workspace"},
  "benchmark": {"id": "swe-bench", "variant": "smoke"}, "comparison": null,
  "execution": {"attempts": 2, "concurrency": 1, "seed": 7, "timeout_seconds": 3600}
}'''
MANIFEST_V5 = {
    'schema_version': 5, 'profile': 'test', 'model_profile': 'offline',
    'models': {'main': {'model': 'offline'}}, 'components': [],
    'context_pipeline': None,
    'base_prompt': {'reference': 'fixture', 'content_hash': 'sha256:fixture'},
    'digest': 'sha256:manifest',
}


class PersistenceContractTests(unittest.TestCase):
    def test_fixed_session_transcript_is_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'session.jsonl'
            path.write_text(SESSION_V1)
            with Session(path) as session:
                self.assertEqual([UserMessage(content='hello')], session.messages())
                self.assertEqual([1], [entry.id for entry in session.read_all()])

    def test_fixed_request_v1_round_trip_and_future_version_rejection(self):
        for payload in (json.loads(REQUEST_V1), request_payload()):
            with self.subTest(source=payload):
                self.assertEqual(payload, EvaluationRequest.from_dict(payload).to_dict())
        for version in (2, 999):
            payload = json.loads(REQUEST_V1)
            payload['schema_version'] = version
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, 'schema_version'):
                EvaluationRequest.from_dict(payload)

    def test_manifest_v5_wire_fields_are_fixed(self):
        manifest = RuntimeManifest(5, 'test', 'offline', {'main': {'model': 'offline'}}, (), None, (),
                                   {'reference': 'fixture', 'content_hash': 'sha256:fixture'}, 'sha256:manifest')
        self.assertEqual(MANIFEST_V5, manifest.to_dict())
        with_artifact = RuntimeManifest(5, 'test', 'offline', {'main': {'model': 'offline'}}, (), None,
                                        ({'artifact_id': 'sha256:fixture'},),
                                        {'reference': 'fixture', 'content_hash': 'sha256:fixture'}, 'sha256:manifest')
        self.assertEqual({**MANIFEST_V5, 'data_artifacts': [{'artifact_id': 'sha256:fixture'}]}, with_artifact.to_dict())

    def test_environment_value_objects_remain_frozen_with_portable_fields(self):
        expected = {
            FileInfo: ('name', 'path', 'kind', 'size', 'mtime_ms'),
            ExecResult: ('stdout', 'stderr', 'exit_code', 'cancelled'),
            ExecOptions: ('cwd', 'env', 'inherit_env', 'timeout_seconds', 'on_stdout', 'on_stderr'),
        }
        for value_type, names in expected.items():
            with self.subTest(type=value_type.__name__):
                self.assertEqual(names, tuple(field.name for field in fields(value_type)))
                self.assertTrue(value_type.__dataclass_params__.frozen)
