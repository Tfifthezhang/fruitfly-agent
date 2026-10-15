"""Back follows the displayed menu hierarchy without starting work."""
import io
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from fruitfly_agent.interactive import TerminalFrontend, EvaluationSnapshot, EvaluationBenchmarkOption, EvaluationVariantOption
from fruitfly_agent.interactive.contracts.optimization import OptimizationPreview
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
        frontend = TerminalFrontend(offline_session(), input_stream=io.StringIO(), output_stream=io.StringIO(),
            improvement_clients=clients or ImprovementClients(), evaluation=benchmark, line_editor=reader)
        frames = []
        pending = list(events)
        def read():
            return pending.pop(0) if pending else QUIT
        frontend.menu_input = SimpleNamespace(read_event=read)
        frontend.menu_renderer = SimpleNamespace(ansi=False, render=lambda **frame: frames.append(frame))
        result = await frontend.improvement_frontend().run(('improve',))
        self.assertEqual(pending, [], 'The menu exited before the scripted Back sequence finished')
        return frames, result

    def services(self):
        search = SimpleNamespace(optimization_preview=Mock(return_value=OptimizationPreview(
            'method', 'Search', 'Costs', preview_token='token')), start_optimization=Mock())
        benchmark = SimpleNamespace(improvement_available=True,
            improvement_snapshot=Mock(return_value=EvaluationSnapshot((EvaluationBenchmarkOption(
                'bench', 'Bench', 'Tasks', 'fixed', (EvaluationVariantOption('cpu', 'CPU', 'Five tasks', True),)),))),
            benchmark_preview=search.optimization_preview, improve=AsyncMock(return_value=()))
        return search, benchmark

    async def test_benchmark_back_and_confirmation_cancel_restore_each_parent(self):
        search, benchmark = self.services()
        frames, _ = await self.menu([pick(), pick(1), pick(), pick(), pick(1), BACK, BACK, BACK, BACK],
            clients=ImprovementClients(search=search), benchmark=benchmark)
        self.assertEqual([f['title'] for f in frames], ['Improvement', 'Choose task source',
            'Choose benchmark tasks', 'Choose task set', 'Confirm improvement', 'Choose task set',
            'Choose benchmark tasks', 'Choose task source', 'Improvement'])
        self.assertEqual(frames[-2]['selected'], 1)
        benchmark.improve.assert_not_awaited()
        search.start_optimization.assert_not_called()

    async def test_quit_from_nested_page_exits_entire_menu(self):
        search, benchmark = self.services()
        frames, _ = await self.menu([pick(), pick(1), QUIT],
            clients=ImprovementClients(search=search), benchmark=benchmark)
        self.assertEqual([f['title'] for f in frames], ['Improvement', 'Choose task source', 'Choose benchmark tasks'])
        benchmark.improve.assert_not_awaited()

    async def test_saved_package_back_restores_source_and_home(self):
        search, benchmark = self.services()
        pack = TaskPackView('pack', 'Pack', 'hash', 1, 1, 1, True)
        materials = SimpleNamespace(task_packs_available=True, task_packs=Mock(return_value=(pack,)))
        frames, _ = await self.menu([pick(), pick(), BACK, BACK, BACK],
            clients=ImprovementClients(search=search, materials=materials), benchmark=benchmark)
        self.assertEqual([f['title'] for f in frames], ['Improvement', 'Choose task source',
            'Choose task package', 'Choose task source', 'Improvement'])
        search.optimization_preview.assert_not_called()

    async def test_package_confirmation_cancel_restores_package_and_direction(self):
        search, _ = self.services()
        pack = TaskPackView('pack', 'Pack', 'hash', 1, 1, 1, True)
        materials = SimpleNamespace(task_packs_available=True, task_packs=Mock(return_value=(pack,)))
        frames, _ = await self.menu([pick(), pick(), pick(1), BACK, BACK],
            clients=ImprovementClients(search=search, materials=materials))
        self.assertEqual([f['title'] for f in frames], ['Improvement', 'Choose task package',
            'Confirm improvement', 'Choose task package', 'Improvement'])
        search.start_optimization.assert_not_called()

    async def test_candidate_detail_back_restores_list_and_home(self):
        view = CandidateView('candidate', 'proposed', 'method', 'text', 'artifact', 'improve', 'parent')
        candidates = SimpleNamespace(candidates=lambda: (view,), candidate_detail=Mock(return_value=(view, 'change')),
            candidate_action=Mock())
        frames, _ = await self.menu([pick(), pick(), BACK, BACK, BACK],
            clients=ImprovementClients(candidates=candidates))
        self.assertEqual([f['title'] for f in frames], ['Improvement', 'Improvement candidates',
            'Candidate candidate · Ready for review', 'Improvement candidates', 'Improvement'])
        candidates.candidate_action.assert_not_called()

    async def test_saved_case_package_back_restores_task_selection(self):
        task = CorrectionView('task', 'question', 'answer', False)
        materials = SimpleNamespace(task_packs_available=True, correction_tasks=lambda: (task,), task_packs=lambda: (),
            save_training_task=Mock())
        frames, _ = await self.menu([pick(), pick(), BACK, BACK, BACK],
            clients=ImprovementClients(materials=materials))
        self.assertEqual([f['title'] for f in frames], ['Improvement', 'Choose completed task',
            'Save to task package', 'Choose completed task', 'Improvement'])
        materials.save_training_task.assert_not_called()

    async def test_saved_case_confirmation_back_preserves_form_draft(self):
        task = CorrectionView('task', 'question', 'answer', False)
        materials = SimpleNamespace(task_packs_available=True, correction_tasks=lambda: (task,), task_packs=lambda: (),
            save_training_task=Mock())
        reader = SimpleNamespace(read_line=Mock(side_effect=['Corrections', 'Complete question', 'Correct answer', 'Reason']))
        frames, _ = await self.menu([pick(), pick(), pick(), pick(1), pick(), pick(1), BACK, BACK, BACK],
            clients=ImprovementClients(materials=materials), reader=reader)
        confirmations = [f for f in frames if f['title'] == 'Confirm training task']
        self.assertEqual(len(confirmations), 2)
        self.assertEqual(confirmations[0]['subtitle'], confirmations[1]['subtitle'])
        self.assertEqual(reader.read_line.call_count, 4)
        self.assertEqual([f['selected'] for f in confirmations], [1, 1])
        materials.save_training_task.assert_not_called()

    async def test_candidate_back_preserves_parent_page_and_selection(self):
        views = tuple(CandidateView(f'candidate-{i}', 'proposed', 'method', 'text', 'artifact', 'improve', 'parent')
                      for i in range(12))
        candidates = SimpleNamespace(candidates=lambda: views,
            candidate_detail=Mock(return_value=(views[-1], 'change')), candidate_action=Mock())
        frames, _ = await self.menu([pick(), pick(10), pick(2), BACK, BACK, BACK],
            clients=ImprovementClients(candidates=candidates))
        lists = [f for f in frames if f['title'] == 'Improvement candidates']
        self.assertIn('page 2/2', lists[-1]['subtitle'])
        self.assertEqual(lists[-1]['selected'], 2)
        candidates.candidate_detail.assert_called_once_with('candidate-11')
        candidates.candidate_action.assert_not_called()
