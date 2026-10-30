"""A submitted program must carry its dependencies and run from frozen files."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest

from fruitfly_agent.lab.improvement.execution import ExecutionContext
from fruitfly_agent.improvement.contracts.experiments import ExecutionRequest
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial, Resource
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.lab.improvement.execution import files
from fruitfly_agent.lab.improvement.execution.deliverables import DeliverySpec, DeliveryBundle
from fruitfly_agent.lab.improvement.verification.delivery import (CommandDeliveryBackend, DeliveryValidationRunner)
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.improvement.execution.facts import read_facts
from tests.support.pipeline import build_pipeline


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_sidecar_is_rejected_and_standalone_bundle_runs_in_clean_directory(self):
        flow, plan, baseline, _ = build_pipeline()
        artifacts, services = MemoryArtifacts(), WorkflowServices(plan)
        script = b'from pathlib import Path\nprint(Path("weights.dat").read_text())\n'
        def reference(path, data):
            return Resource('deliverables/' + path, artifacts.put(data), 'application/octet-stream', 'deliverable')
        record = ExecutionRecord('delivery', 'task', TaskMaterial('task', 'Work').material_id,
            baseline.snapshot_id, plan.parent.state, plan.conditions_id, 'completed', 'Done',
            (reference('main.py', script),))
        task = TaskMaterial('task', 'Work')
        class Runner:
            capabilities = frozenset()
            async def execute(self, *args): return record
        runner = DeliveryValidationRunner(Runner(), DeliverySpec('main.py', ('weights.dat',)),
            CommandDeliveryBackend((sys.executable,)), artifacts, services)
        try:
            missing = await runner.execute(plan, task, baseline)
            self.assertEqual(missing.status, 'error')
            self.assertTrue(read_facts(missing, artifacts).diagnosable)
            receipt = next(r for r in missing.artifacts if r.path == 'delivery-validation.json')
            self.assertIn('weights.dat', artifacts.read(receipt.artifact_id).decode())
            record = replace(record, artifacts=(*record.artifacts, reference('weights.dat', b'42')))
            valid = await runner.execute(plan, task, baseline)
            self.assertEqual(valid.status, 'completed')
            receipt = next(r for r in valid.artifacts if r.path == 'delivery-validation.json')
            value = json.loads(artifacts.read(receipt.artifact_id))
            self.assertEqual(value['result']['stdout'], '42\n')
            self.assertEqual(value['result']['exit_code'], 0)
            self.assertTrue(value['result']['bundle_id'])
            self.assertEqual(len(value['bundle']['files']), 2)
            # All immutable versions remain independently readable.
            self.assertEqual(artifacts.read(missing.artifacts[-1].artifact_id), read_facts(missing, artifacts).serialize())
        finally:
            await services.close()

    async def test_undeclared_dependency_cannot_be_borrowed_from_working_directory(self):
        flow, plan, baseline, _ = build_pipeline()
        artifacts = MemoryArtifacts()
        task = TaskMaterial('task', 'Work')
        code = b'from pathlib import Path\nprint(Path("ambient-only.dat").read_text())\n'
        record = ExecutionRecord('delivery', 'task', task.material_id, baseline.snapshot_id,
            plan.parent.state, plan.conditions_id, 'completed', artifacts=(
                Resource('deliverables/main.py', artifacts.put(code), 'text/plain', 'deliverable'),))
        bundle = DeliveryBundle.collect(record, task, DeliverySpec('main.py'))
        result = await CommandDeliveryBackend((sys.executable,)).validate(bundle, artifacts)
        self.assertEqual(result.status, 'failed')
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(result.stdout, '')
        self.assertIn('FileNotFoundError', result.stderr)

    async def test_explicit_file_manifest_is_preflighted_and_wraps_actual_runner(self):
        flow, plan, baseline, _ = build_pipeline()
        artifacts, services = MemoryArtifacts(), WorkflowServices(plan)
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'delivery.json').write_text(json.dumps({'entrypoint': 'answer.txt'}))
            context = ExecutionContext(directory, artifacts, flow.components, None, None, None,
                plan=plan, services=services)
            request = ExecutionRequest('Write a deliverable.', ('delivery.json',), ('prompt',), '', 'task', 'behavior',
                (('delivery_manifest', 'delivery.json'),))
            with self.assertRaisesRegex(ValueError, 'backend'):
                files.prepare(context, request)
            context.delivery_backend = CommandDeliveryBackend(('/bin/cat',))
            prepared = files.prepare(context, request)
            class Runner:
                capabilities = frozenset()
                async def execute(self, plan, task, harness):
                    return ExecutionRecord('delivery', task.task_id, task.material_id, harness.snapshot_id,
                        plan.parent.state, plan.conditions_id, 'completed', artifacts=(Resource('deliverables/answer.txt',
                            artifacts.put(b'answer'), 'text/plain', 'deliverable'),))
            context.runner_factory = lambda *args: Runner()
            ports = files.build(context, prepared)
            self.assertIn('delivery-validation', ports.runner.capabilities)
            record = await ports.runner.execute(plan, prepared.task, baseline)
            self.assertEqual(record.status, 'completed')
            self.assertEqual(read_facts(record, artifacts).termination_reason, 'delivery_passed')
        await services.close()

    def test_delivery_manifest_rejects_escape_duplicates_unknown_fields_and_bad_types(self):
        for value in ('{"entrypoint":"../outside"}', '{"entrypoint":"a","entrypoint":"b"}',
                      '{"entrypoint":"a","unknown":1}', '{"entrypoint":"a","dependencies":"abc"}',
                      '{"entrypoint":"a","timeout_seconds":true}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                DeliverySpec.parse(value)

    def test_backend_command_parameters_join_frozen_identity(self):
        from fruitfly_agent.lab.improvement.workflow.mechanisms import extension_spec
        backend = CommandDeliveryBackend(('/bin/cat',))
        frozen = extension_spec(backend)
        backend.command = ('/bin/echo',)
        self.assertNotEqual(extension_spec(backend), frozen)
        self.assertEqual(frozen['configuration']['command'], ['/bin/cat'])
        with self.assertRaisesRegex(ValueError, 'configuration'):
            extension_spec(object())
