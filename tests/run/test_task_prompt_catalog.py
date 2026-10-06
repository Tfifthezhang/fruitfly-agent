"""Task-specific outputs and prompt menus preserve identities without exposing storage."""
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from fruitfly_agent.interactive.configuration import ConfigurationSnapshot
from fruitfly_agent.interactive.terminal.menu import RawTerminalMenuInput
from fruitfly_agent.run.artifacts import DataArtifactStore
from fruitfly_agent.run.optimization import CandidateStore
from fruitfly_agent.run.retention import compact_candidates
from fruitfly_agent.run.task_results import save_task_result
from fruitfly_agent.run.profiles import RunConfigurationController, resolve_harness_selection
from fruitfly_agent.lab.catalog import builtin_catalog
from fruitfly_agent.lab.base_prompt import DEFAULT_PROMPT, builtins
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.interactive.terminal.configuration import TerminalConfigurationFrontend
from tests.support.run import _write_catalog


class TaskPromptTests(unittest.TestCase):
    def test_each_task_keeps_latest_and_menu_filters_scope_and_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / 'models.yaml', {'local': 'model-a'})
            catalog = builtin_catalog()
            selection = resolve_harness_selection(cwd=root, config_path=None, profile_id=None,
                                                 environment={}, catalog=catalog)
            artifacts = DataArtifactStore(root / '.fruitfly/artifacts')
            store = CandidateStore(root / '.fruitfly/optimization/candidates', artifacts)
            controller = RunConfigurationController(selection, catalog, artifacts)
            def create(text, task, **overrides):
                args = dict(text=text, algorithm='opro', parent_manifest={'digest':'parent'},
                            cases_digest='cases', direction='improve', seed_score=0, validation_score=1,
                            metric_calls=2, snapshot=BasePromptTarget('original').snapshot(),
                            config_path=str(selection.config_path.resolve()), profile_id='default',
                            task_pack_id=task, task_pack_name=task + ' tasks')
                return store.create(**{**args, **overrides})
            old = create('A old', 'python')
            create('B current', 'tickets')
            new = create('A current', 'python')
            artifacts.put_text('unattributed text')
            artifacts.put_text(DEFAULT_PROMPT.text)
            other = create('other profile', 'python', profile_id='other')
            removed = compact_candidates(root, store, selection.config_path)
            self.assertIn(old.candidate_id, removed)
            self.assertEqual(3, len(store.list()))
            snapshot = controller.snapshot()
            self.assertEqual(len(builtins()) + 2, len(snapshot.prompt_options))
            self.assertEqual(tuple(p.prompt_id for p in builtins()), snapshot.prompt_option_groups[0][2])
            self.assertFalse(snapshot.prompt_option_groups[0][3])
            self.assertEqual(set(snapshot.prompt_options) - set(snapshot.prompt_option_groups[0][2]),
                             set(snapshot.prompt_option_groups[1][2]))
            self.assertTrue(snapshot.prompt_option_groups[1][3])
            self.assertNotIn(other.artifact_id, snapshot.prompt_options)
            label = dict(snapshot.prompt_option_labels)[new.artifact_id]
            self.assertEqual('python tasks · OPRO optimized · proposed', label)
            self.assertEqual(label, controller.preview_prompt(new.artifact_id)[0])
            directory = save_task_result(root, new, 'A current')
            self.assertEqual('A current', (directory / 'latest.txt').read_text())
            save_task_result(root, replace(new, direction='new direction'), 'A current')
            self.assertEqual('new direction', json.loads((directory / 'latest.json').read_text())['direction'])
            self.assertEqual(2, len(tuple(directory.iterdir())))

    def test_legacy_task_label_comes_from_verified_snapshot_without_rewriting(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifacts = DataArtifactStore(root / '.fruitfly/artifacts')
            store = CandidateStore(root / '.fruitfly/optimization/candidates', artifacts)
            path = root / '.fruitfly/optimization/task-snapshots/frozen.json'
            path.parent.mkdir(parents=True)
            encoded = json.dumps({'task': {'pack_id': 'python', 'cases_digest': 'cases'},
                                  'preview': [['Cases', 'Python regression tasks']]})
            path.write_text(encoded)
            record = store.create(text='candidate', algorithm='opro', parent_manifest={'digest':'parent'},
                cases_digest='cases', direction='improve', seed_score=0, validation_score=1, metric_calls=2,
                snapshot=BasePromptTarget('original').snapshot(), evidence=(
                    ('Task snapshot', str(path.relative_to(root))),
                    ('Task snapshot hash', 'sha256:' + hashlib.sha256(encoded.encode()).hexdigest())))
            raw = (store.root / (record.candidate_id + '.json')).read_bytes()
            migrated = store.read(record.candidate_id)
            self.assertEqual(('python', 'Python regression tasks'),
                             (migrated.task_pack_id, migrated.task_pack_name))
            self.assertEqual(raw, (store.root / (record.candidate_id + '.json')).read_bytes())
            path.write_text(encoded + ' ')
            self.assertEqual('', store.read(record.candidate_id).task_pack_name)

    def test_result_export_rejects_relocated_directory(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            (root / '.fruitfly/optimization').mkdir(parents=True)
            (root / '.fruitfly/optimization/task-results').symlink_to(outside, target_is_directory=True)
            record = SimpleNamespace(task_pack_id='python', config_path='config', profile_id='default', target='base_prompt')
            with self.assertRaises(ValueError):
                save_task_result(root, record, 'text')
            self.assertEqual([], list(Path(outside).iterdir()))

    def test_terminal_displays_labels_but_returns_opaque_reference(self):
        stream = io.StringIO('2\n')
        output = io.StringIO()
        frontend = TerminalConfigurationFrontend(SimpleNamespace(), input_stream=stream, output_stream=output)
        _, value = frontend._choose_value(title='Base prompt', subtitle='Choose',
                    values=('assistant-default', 'opaque'), current='assistant-default',
                    labels={'opaque': 'Python tasks · OPRO optimized'})
        self.assertEqual('opaque', value)
        self.assertIn('Python tasks · OPRO optimized', output.getvalue())
        self.assertNotIn('2.   opaque', output.getvalue())

    def _grouped_frontend(self, events):
        snapshot = ConfigurationSnapshot('config', 'default', ('default',), 'models', 'local', ('local',), (),
            prompt_options=('builtin', 'opaque-python', 'opaque-tickets'), prompt_reference='builtin',
            prompt_option_labels=(('builtin', 'Assistant default'), ('opaque-python', 'Python adapted'),
                                  ('opaque-tickets', 'Tickets adapted')),
            prompt_option_groups=(('builtin', 'Built-in prompts', ('builtin',), False),
                                  ('adapted', 'Task / scenario adapted prompts', ('opaque-python', 'opaque-tickets'), True)))
        controller = SimpleNamespace(snapshot=lambda: snapshot,
            preview_prompt=Mock(return_value=('Python adapted', 'verified-hash', 'complete text')),
            select_prompt=Mock())
        sequence = iter(events)
        output = io.StringIO()
        frontend = TerminalConfigurationFrontend(controller, input_stream=io.StringIO(), output_stream=output,
            menu_input=SimpleNamespace(read_event=lambda: RawTerminalMenuInput.decode(next(sequence))))
        frontend.renderer.ansi = True
        return frontend, controller, output

    def test_adapted_dropdown_collapsed_and_expanding_does_not_apply(self):
        frontend, controller, output = self._grouped_frontend((b'\x1b[B', b'\r', b'\x1b'))
        self.assertFalse(frontend._choose_prompt(controller.snapshot()))
        frames = output.getvalue().split('\x1b[2J\x1b[H')
        self.assertIn('Task / scenario adapted prompts ▾', frames[1])
        self.assertNotIn('Python adapted', frames[1])
        self.assertIn('Python adapted', frames[-1])
        self.assertIn('Tickets adapted', frames[-1])
        controller.preview_prompt.assert_not_called()
        controller.select_prompt.assert_not_called()

    def test_adapted_selection_previews_then_confirms_opaque_reference(self):
        for accept in (False, True):
            events = [b'\x1b[B', b'\r', b'\x1b[B', b'\r']
            events += [b'\x1b[A', b'\r'] if accept else [b'\r', b'\x1b']
            frontend, controller, output = self._grouped_frontend(events)
            self.assertFalse(frontend._choose_prompt(controller.snapshot()))
            controller.preview_prompt.assert_called_once_with('opaque-python')
            if accept:
                controller.select_prompt.assert_called_once_with('opaque-python')
            else:
                controller.select_prompt.assert_not_called()
            self.assertIn('complete text', output.getvalue())
            self.assertNotIn('opaque-python', output.getvalue())

    def test_ungrouped_controller_still_supports_prompt_selection(self):
        frontend, controller, output = self._grouped_frontend((b'\r', b'\x1b[A', b'\r'))
        snapshot = replace(controller.snapshot(), prompt_option_groups=())
        controller.snapshot = lambda: snapshot
        self.assertFalse(frontend._choose_prompt(snapshot))
        controller.select_prompt.assert_called_once_with('builtin')

    def test_numbered_dropdown_can_select_second_task(self):
        frontend, controller, output = self._grouped_frontend(())
        from fruitfly_agent.interactive.terminal.menu import LineMenuInput
        editor = SimpleNamespace(read_line=iter(('2', '4', '1')).__next__)
        frontend.menu_input = LineMenuInput(editor)
        frontend.renderer.ansi = False
        self.assertFalse(frontend._choose_prompt(controller.snapshot()))
        controller.preview_prompt.assert_called_once_with('opaque-tickets')
        controller.select_prompt.assert_called_once_with('opaque-tickets')

    def test_current_adaptation_is_named_even_when_dropdown_is_closed(self):
        frontend, controller, output = self._grouped_frontend((b'\x1b',))
        snapshot = replace(controller.snapshot(), prompt_reference='opaque-python')
        controller.snapshot = lambda: snapshot
        self.assertFalse(frontend._choose_prompt(snapshot))
        self.assertIn('✓ Task / scenario adapted prompts ▾', output.getvalue())
        self.assertIn('Python adapted', output.getvalue())
        self.assertNotIn('opaque-python', output.getvalue())
        controller.select_prompt.assert_not_called()
