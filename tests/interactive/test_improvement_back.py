"""Back follows the displayed menu hierarchy without starting work."""
import io
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from fruitfly_agent.interactive import TerminalFrontend, EvaluationSnapshot, EvaluationBenchmarkOption, EvaluationVariantOption
from fruitfly_agent.interactive.contracts.improvement import ImprovementPreview, ImprovementTargetView, ImprovementMethodView
from fruitfly_agent.interactive.contracts.candidates import CandidateView
from fruitfly_agent.interactive.contracts.task_packs import TaskPackView, CorrectionView
from fruitfly_agent.interactive.terminal.bindings import ImprovementClients
from fruitfly_agent.interactive.terminal.io.menu import MenuAction, MenuEvent
from tests.support.application import offline_session


def pick(index=0):
    return MenuEvent(MenuAction.ACTIVATE, index)

BACK = MenuEvent(MenuAction.BACK)
QUIT = MenuEvent(MenuAction.QUIT)


class ImprovementBackTests(unittest.IsolatedAsyncioTestCase):
    async def menu(self, events, *, clients=None, benchmark=None, reader=None):
        clients = replace(clients or ImprovementClients(), targets=lambda: (
            ImprovementTargetView('H', 'base_prompt', 'Base prompt'),))
        frontend = TerminalFrontend(offline_session(), input_stream=io.StringIO(), output_stream=io.StringIO(),
            improvement_clients=clients or ImprovementClients(), evaluation=benchmark, line_editor=reader)
        frames = []
        pending = [pick(), pick(), *events]
        def read():
            return pending.pop(0) if pending else QUIT
        frontend.menu_input = SimpleNamespace(read_event=read)
        frontend.menu_renderer = SimpleNamespace(ansi=False, render=lambda **frame: frames.append(frame))
        result = await frontend.improvement_frontend().run(('improve',))
        self.assertEqual(pending, [], 'The menu exited before the scripted Back sequence finished')
        return frames, result

    def services(self):
        search = SimpleNamespace(improvement_preview=Mock(return_value=ImprovementPreview(
            'method', 'Search', 'Costs', target='base_prompt', preview_token='token')), start_improvement=Mock())
        benchmark = SimpleNamespace(improvement_available=True,
            improvement_snapshot=Mock(return_value=EvaluationSnapshot((EvaluationBenchmarkOption(
                'bench', 'Bench', 'Tasks', 'fixed', (EvaluationVariantOption('cpu', 'CPU', 'Five tasks', True),)),))),
            benchmark_preview=search.improvement_preview, improve=AsyncMock(return_value=()))
        return search, benchmark

    async def test_benchmark_back_and_confirmation_cancel_restore_each_parent(self):
        search, benchmark = self.services()
        frames, _ = await self.menu([pick(), pick(1), pick(), pick(), pick(1), BACK, BACK, BACK, BACK],
            clients=ImprovementClients(search=search), benchmark=benchmark)
        self.assertEqual([f['title'] for f in frames], ['Improvement', 'H · Choose target', 'H · Base prompt', 'Choose task source',
            'Choose benchmark tasks', 'Choose task set', 'Confirm improvement', 'Choose task set',
            'Choose benchmark tasks', 'Choose task source', 'H · Base prompt', 'H · Choose target'])
        self.assertEqual(next(f for f in reversed(frames) if f['title'] == 'Choose task source')['selected'], 1)
        benchmark.improve.assert_not_awaited()
        search.start_improvement.assert_not_called()

    async def test_quit_from_nested_page_exits_entire_menu(self):
        search, benchmark = self.services()
        frames, _ = await self.menu([pick(), pick(1), QUIT],
            clients=ImprovementClients(search=search), benchmark=benchmark)
        self.assertEqual([f['title'] for f in frames], ['Improvement', 'H · Choose target', 'H · Base prompt', 'Choose task source', 'Choose benchmark tasks'])
        benchmark.improve.assert_not_awaited()

    async def test_saved_package_back_restores_source_and_home(self):
        search, benchmark = self.services()
        pack = TaskPackView('pack', 'Pack', 'hash', 1, 1, 1, True)
        materials = SimpleNamespace(task_packs_available=True, task_packs=Mock(return_value=(pack,)))
        frames, _ = await self.menu([pick(), pick(), BACK, BACK, BACK],
            clients=ImprovementClients(search=search, materials=materials), benchmark=benchmark)
        self.assertEqual([f['title'] for f in frames], ['Improvement', 'H · Choose target', 'H · Base prompt', 'Choose task source',
            'Choose task package', 'Choose task source', 'H · Base prompt', 'H · Choose target'])
        search.improvement_preview.assert_not_called()

    async def test_package_confirmation_cancel_restores_package_and_direction(self):
        search, _ = self.services()
        pack = TaskPackView('pack', 'Pack', 'hash', 1, 1, 1, True)
        materials = SimpleNamespace(task_packs_available=True, task_packs=Mock(return_value=(pack,)))
        frames, _ = await self.menu([pick(), pick(), pick(1), BACK, BACK],
            clients=ImprovementClients(search=search, materials=materials))
        self.assertEqual([f['title'] for f in frames], ['Improvement', 'H · Choose target', 'H · Base prompt', 'Choose task package',
            'Confirm improvement', 'Choose task package', 'H · Base prompt', 'H · Choose target'])
        search.start_improvement.assert_not_called()

    async def test_candidate_detail_back_restores_list_and_home(self):
        view = CandidateView('candidate', 'proposed', 'method', 'base_prompt', 'artifact', 'improve', 'parent')
        candidates = SimpleNamespace(candidates=lambda: (view,), candidate_detail=Mock(return_value=(view, 'change')),
            candidate_action=Mock())
        frames, _ = await self.menu([pick(1), pick(), BACK, BACK, BACK],
            clients=ImprovementClients(candidates=candidates))
        self.assertEqual([f['title'] for f in frames], ['Improvement', 'H · Choose target', 'H · Base prompt', 'Improvement candidates',
            'Candidate candidate · Ready for review', 'Improvement candidates', 'H · Base prompt', 'H · Choose target'])
        candidates.candidate_action.assert_not_called()

    async def test_material_capture_is_not_an_improvement_menu_action(self):
        materials = SimpleNamespace(task_packs_available=True, correction_tasks=Mock(), save_training_task=Mock())
        frames, _ = await self.menu([BACK], clients=ImprovementClients(materials=materials))
        labels = [row.label for frame in frames for row in frame['rows']]
        self.assertNotIn('Save a failed task', labels)
        materials.correction_tasks.assert_not_called()
        materials.save_training_task.assert_not_called()

    async def test_candidate_back_preserves_parent_page_and_selection(self):
        views = tuple(CandidateView(f'candidate-{i}', 'proposed', 'method', 'base_prompt', 'artifact', 'improve', 'parent')
                      for i in range(12))
        candidates = SimpleNamespace(candidates=lambda: views,
            candidate_detail=Mock(return_value=(views[-1], 'change')), candidate_action=Mock())
        frames, _ = await self.menu([pick(1), pick(10), pick(2), BACK, BACK, BACK],
            clients=ImprovementClients(candidates=candidates))
        lists = [f for f in frames if f['title'] == 'Improvement candidates']
        self.assertIn('page 2/2', lists[-1]['subtitle'])
        self.assertEqual(lists[-1]['selected'], 2)
        candidates.candidate_detail.assert_called_once_with('candidate-11')
        candidates.candidate_action.assert_not_called()


    async def test_method_back_unavailable_choice_and_selected_preview(self):
        search, _ = self.services()
        methods = (
            ImprovementMethodView('method', 'Default method', 'Configured method', default=True),
            ImprovementMethodView('missing', 'Unavailable method', '', False, 'Missing executor'),
            ImprovementMethodView('alternative', 'Alternative', 'Another registered method'))
        search.improvement_preview.return_value = replace(search.improvement_preview.return_value, algorithm='alternative')
        clients = ImprovementClients(search=search, methods=lambda role, target: methods)
        frames, result = await self.menu([pick(), pick(1), pick(2), pick(1), BACK, BACK], clients=clients)
        self.assertIn('Choose improvement method', [f['title'] for f in frames])
        self.assertIn('Missing executor', ''.join(f.get('notice', '') for f in frames))
        search.improvement_preview.assert_called_once_with(pack_id=None, direction='improve',
            method_id='alternative', target_id='base_prompt')
        search.start_improvement.assert_not_called()

    async def test_improver_role_uses_same_method_preview_and_submission_flow(self):
        search = SimpleNamespace(improvement_preview=Mock(return_value=ImprovementPreview(
            'policy-method', 'Policy method', 'Bounded policy comparison',
            target='policy-target', preview_token='receipt', role='I')), start_improvement=Mock())
        clients = ImprovementClients(search=search,
            targets=lambda: (ImprovementTargetView('I', 'policy-target', 'Exploration policy'),),
            methods=lambda role, target: (ImprovementMethodView('policy-method', 'Policy method', 'Compare policies'),))
        frontend = TerminalFrontend(offline_session(), input_stream=io.StringIO(), output_stream=io.StringIO(),
            improvement_clients=clients)
        events = [pick(2), pick(), pick(), pick()]
        frontend.menu_input = SimpleNamespace(read_event=lambda: events.pop(0))
        frames = []
        frontend.menu_renderer = SimpleNamespace(ansi=False, render=lambda **frame: frames.append(frame))
        result = await frontend.improvement_frontend().run(('Improve',))
        self.assertIn('Improvement submitted', result)
        search.improvement_preview.assert_called_once_with(pack_id=None, direction='Improve',
            method_id='policy-method', target_id='policy-target')
        search.start_improvement.assert_called_once_with('Improve', preview_token='receipt')
        self.assertEqual(events, [])

    async def test_edit_job_parameters_repreviews_before_explicit_start(self):
        from tests.support.terminal import ScriptedLines
        search, _ = self.services()
        clients = ImprovementClients(search=search, methods=lambda role, target: (
            ImprovementMethodView('method', 'Method', 'Registered method'),))
        frames, result = await self.menu([pick(), pick(2), pick()], clients=clients,
            reader=ScriptedLines('{"rounds": 1, "max_model_calls": 8}'))
        self.assertEqual(search.improvement_preview.call_count, 3)
        self.assertEqual(search.improvement_preview.call_args.kwargs['parameters'],
                         {'rounds': 1, 'max_model_calls': 8})
        search.start_improvement.assert_called_once_with('improve', preview_token='token')
        self.assertIn('Improvement submitted', result)

    async def test_invalid_parameter_edits_do_not_start_work(self):
        from tests.support.terminal import ScriptedLines
        search, _ = self.services()
        clients = ImprovementClients(search=search, methods=lambda role, target: (
            ImprovementMethodView('method', 'Method', 'Registered method'),))
        frames, result = await self.menu([pick(), pick(2), pick(1), BACK, BACK], clients=clients,
            reader=ScriptedLines('[]'))
        self.assertIn('Invalid parameters', result)
        search.start_improvement.assert_not_called()
