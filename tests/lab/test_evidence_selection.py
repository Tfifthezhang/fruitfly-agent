"""Selection candidates change actual grants without mutating retained evidence."""
from dataclasses import replace, asdict
import json
import unittest
import yaml
from fruitfly_agent.lab.improvement.evidence_selection import RepresentativeSelector, SelectionSettings
from fruitfly_agent.lab.improvement.evidence_selection.improvement import SelectionTarget, candidate_selector
from fruitfly_agent.lab.improvement.components.text import TextComponentAdapter
from fruitfly_agent.improvement.contracts.components import ComponentFile
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial, Resource
from fruitfly_agent.improvement.contracts.organization import OrganizationRequest
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.lab.improvement.organizer.workspace import build_workspace
from tests.support.stages import proposal_fixture, Runner


def row(run, task, **changes):
    return {'run_id': run, 'task_id': task, 'status': 'completed', 'diagnostics_complete': True,
            'elapsed_seconds': 1, 'model_calls': 1, 'observations': [], **changes}


class SelectionTests(unittest.IsolatedAsyncioTestCase):
    def test_frozen_source_loads_policy_and_default_resources_without_checkout(self):
        import tempfile
        import subprocess
        import sys
        from pathlib import Path
        from fruitfly_agent.run.storage.snapshots import capture_source_tree
        root = Path(__file__).resolve().parents[2]
        source = capture_source_tree(root)
        self.assertIn('fruitfly_agent/lab/improvement/evidence_selection/methods/representative/defaults.yaml',
                      {f.path for f in source.files})
        with tempfile.TemporaryDirectory() as tmp:
            frozen = Path(tmp)
            for entry in source.files:
                path = frozen / entry.path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(entry.content)
            code = """import sys, pathlib
sys.path.insert(0, sys.argv[1])
from fruitfly_agent.lab.improvement.evidence_selection import RepresentativeSelector, SelectionSettings
import fruitfly_agent.lab.improvement.evidence_selection as owner
assert pathlib.Path(owner.__file__).is_relative_to(sys.argv[1])
assert SelectionSettings().max_cases == 8
result = RepresentativeSelector().select(({'run_id':'frozen','task_id':'task','status':'timeout'},))
assert result['selected'][0]['run_id'] == 'frozen'
"""
            result = subprocess.run([sys.executable, '-I', '-c', code, str(frozen)],
                cwd=frozen, text=True, capture_output=True, timeout=20)
            self.assertEqual(0, result.returncode, result.stderr)

    def test_resource_signals_use_execution_scopes_without_double_counting(self):
        selector = RepresentativeSelector()
        turn = row('turn', 'a', usage=[{'resource': 'input_tokens', 'scope': 'turn', 'used': 999999}])
        execution = row('execution', 'b', usage=[{'resource': 'input_tokens', 'scope': 'execution', 'used': 999999}])
        tools = row('tools', 'c', counters={'tool_started': 90})
        result = selector.select((turn, execution, tools))
        self.assertEqual({'execution', 'tools'}, {r['run_id'] for r in result['selected']})

    def test_authorized_material_policy_changes_actual_detail_grants(self):
        from fruitfly_agent.improvement.contracts.versions import content_hash
        resources = (Resource('diagnostics/capture-manifest.json', content_hash('catalog'), kind='diagnostic'),
                     Resource('agent/0/reading-trajectory.jsonl', content_hash('trajectory'), kind='trajectory'))
        owner = SelectionTarget()
        adapter = TextComponentAdapter(owner, owner.component_kind)
        original = adapter.snapshot()
        values = yaml.safe_load(original.files[0].text)
        values['parameters']['settings']['material_policy'] = 'all-granted'
        candidate = replace(original, files=(ComponentFile('parameters.yaml', yaml.safe_dump(values)),))
        trial = candidate_selector(candidate, options={'editable_fields': ['parameters.settings.material_policy']})
        rows = (row('case', 'task', status='timeout'),)
        focused = RepresentativeSelector().select(rows, resources={'case': resources})
        complete = trial.select(rows, resources={'case': resources})
        self.assertEqual(['agent/0/reading-trajectory.jsonl'], focused['selected'][0]['material_paths'])
        self.assertEqual(2, len(complete['selected'][0]['material_paths']))
        self.assertEqual(original, adapter.snapshot())

    def test_candidate_changes_actual_selection_identity_and_preserves_protected_fields(self):
        owner = SelectionTarget()
        adapter = TextComponentAdapter(owner, owner.component_kind)
        original = adapter.snapshot()
        values = yaml.safe_load(original.files[0].text)
        values['parameters']['settings']['many_calls'] = 2
        candidate = replace(original, files=(ComponentFile('parameters.yaml', yaml.safe_dump(values)),))
        grant = {'editable_fields': ['parameters.settings.many_calls'],
                 'bounds': {'parameters.settings.many_calls': {'minimum': 2, 'maximum': 10}}}
        trial = candidate_selector(candidate, options=grant)
        records = (row('fast', 'a'), row('calls', 'b', model_calls=3))
        self.assertEqual([], RepresentativeSelector().select(records)['selected'])
        self.assertEqual('calls', trial.select(records)['selected'][0]['run_id'])
        self.assertNotEqual(trial.identity, RepresentativeSelector().identity)
        self.assertEqual(original, adapter.snapshot())
        with self.assertRaisesRegex(ValueError, 'protected'):
            candidate_selector(candidate, options={'editable_fields': ['parameters.settings.slow_seconds']})
        with self.assertRaisesRegex(ValueError, 'bounds'):
            candidate_selector(candidate, options={'editable_fields': ['parameters.settings.many_calls'],
                'bounds': {'parameters.settings.many_calls': {'minimum': 5}}})
        with self.assertRaises(ValueError):
            candidate_selector(replace(candidate, role='H'), options=grant)

    def test_controls_rare_signals_unknowns_and_hard_limits(self):
        rows = [row('control', 'control', observations=[{'name': 'official_reward', 'value': {'reward': 1}}])]
        rows.extend(row('common-' + str(i), 'same', model_calls=99) for i in range(20))
        rows.extend((row('rare', 'rare', status='timeout'), row('unknown', 'unknown', diagnostics_complete=None)))
        selector = RepresentativeSelector(SelectionSettings(max_cases=4, max_per_task=1))
        result = selector.select(tuple(rows))
        self.assertEqual(4, len(result['selected']))
        self.assertEqual({'control', 'rare', 'unknown', 'common-0'}, {r['run_id'] for r in result['selected']})
        self.assertEqual(19, result['omitted_executions'])
        self.assertEqual(result, selector.select(tuple(reversed(rows))))
        self.assertEqual([], selector.select((row('completed', 'a'),))['selected'])

    async def test_workspaces_keep_all_summaries_but_only_selected_originals(self):
        _, plan, baseline, _ = proposal_fixture()
        tasks = (TaskMaterial('a', 'Selected task'), TaskMaterial('b', 'Excluded task'))
        runner, artifacts = Runner(), MemoryArtifacts()
        records = tuple([await runner.execute(plan, task, baseline) for task in tasks])
        selection = {'selected': [{'run_id': records[0].run_id}], 'omitted_executions': 1}
        resource = Resource('selection.json', artifacts.put(json.dumps(selection).encode()))
        request = OrganizationRequest(tasks, records, context=(resource,))
        workspace, batch = build_workspace(request, artifacts)
        self.assertEqual(['a'], [t['task_id'] for t in batch['tasks']])
        self.assertEqual(2, len(json.loads(workspace.read('context/executions.json'))))
        self.assertNotIn('context/tasks/b/task.md', workspace.paths())
        self.assertNotIn('context/executions/' + records[1].run_id + '/output.txt', workspace.paths())
        self.assertEqual(records[0].output.encode(), workspace.read('context/executions/' + records[0].run_id + '/output.txt'))
        self.assertNotIn('output', json.loads(workspace.read('context/executions/' + records[0].run_id + '/metadata.json')))
        from fruitfly_agent.improvement.contracts.editing import ResearchProposalRequest
        from fruitfly_agent.lab.improvement.evidence.research import build_workspace as editor_workspace
        editor = editor_workspace(ResearchProposalRequest(plan, tasks, baseline, records, (resource,)), artifacts)
        self.assertNotIn('context/tasks/b/metadata.json', editor.paths())
        self.assertEqual(2, len(json.loads(editor.read('context/executions.json'))))
        self.assertEqual(request.records, records)

    async def test_candidate_reasons_must_reference_supplied_issues_and_read_originals(self):
        from fruitfly_agent.improvement.contracts.editing import ResearchProposalRequest
        from fruitfly_agent.lab.improvement.evidence.research import build_workspace as editor_workspace
        from fruitfly_agent.lab.improvement.evidence.catalog import WorkspaceEvidence
        from fruitfly_agent.lab.improvement.editor.submission import submission
        flow, plan, baseline, _ = proposal_fixture()
        components = flow.components
        task, artifacts = TaskMaterial('task', 'Inspect'), MemoryArtifacts()
        record = await Runner().execute(plan, task, baseline)
        guide = Resource('organization/guide.json', artifacts.put(json.dumps({'findings': [
            {'issue_id': 'observed-omission', 'facts': ['Missing inspection']}]}).encode()))
        request = ResearchProposalRequest(plan, (task,), baseline, (record,), (guide,))
        workspace = editor_workspace(request, artifacts)
        workspace.write('harness/prompt/instructions.txt', 'Improved inspection')
        reader = WorkspaceEvidence(workspace)
        reader.read('context/executions/' + record.run_id + '/output.txt')
        reason = {'component_id': 'prompt', 'explanation': 'Observed omission',
                  'expected_effect': 'Inspect before responding; disconfirm with another omission',
                  'evidence_ids': [record.run_id], 'issue_ids': ['observed-omission']}
        candidate = submission({'reasons': [reason]}, workspace, request, components)
        self.assertEqual(('observed-omission',), candidate.reasons[0].issue_ids)
        for issue_ids in ([], ['invented-issue']):
            with self.assertRaisesRegex(ValueError, 'findings'):
                submission({'reasons': [{**reason, 'issue_ids': issue_ids}]}, workspace, request, components)

    async def test_batch_loading_does_not_hydrate_originals_and_deduplicates_observations(self):
        import tempfile
        from fruitfly_agent.run.improvement.service import ResearchService
        from fruitfly_agent.improvement.contracts.research import ResearchBatch
        from fruitfly_agent.improvement.contracts.versions import content_hash
        _, plan, baseline, _ = proposal_fixture()
        task, artifacts = TaskMaterial('task', 'Inspect'), MemoryArtifacts()
        record = await Runner().execute(plan, task, baseline)
        record = replace(record, artifacts=(Resource('unavailable-original.txt', content_hash('not retained')),))
        observation = {'run_id': record.run_id, 'name': 'unknown', 'value': None}
        with tempfile.TemporaryDirectory() as tmp:
            service = ResearchService(tmp, 'lazy', artifacts)
            resource = service.put('batch.json', ResearchBatch((task,), (record,), (observation,)).to_dict())
            merged = service.input_batch((resource, resource))
            self.assertEqual((record,), merged.records)
            self.assertEqual((observation,), merged.observations)

    def test_catalog_configuration_round_trip_and_grants(self):
        from fruitfly_agent.lab.catalog import builtin_catalog
        from fruitfly_agent.lab.catalog.defaults import read_default
        from fruitfly_agent.lab.catalog.configuration import configuration_surfaces
        catalog = builtin_catalog()
        document, receipt = read_default(catalog, 'improvement-evidence-selection')
        self.assertIsNotNone(receipt)
        surface = configuration_surfaces(catalog)[document.id][1]
        self.assertEqual('I', surface.role)
        self.assertEqual(dict(document.parameters), surface.normalize(dict(document.parameters)))
        self.assertEqual({'settings': asdict(SelectionSettings())}, surface.restore({}, json.dumps(document.parameters)))
        surface.edit_options(['parameters.settings.max_cases'], {'parameters.settings.max_cases': {'maximum': 12}})
        with self.assertRaises(ValueError):
            surface.normalize({'settings': {'max_cases': True}})
