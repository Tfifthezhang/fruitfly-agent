"""The experiment panel keeps editing one level deep and preserves its draft."""
import asyncio
import io
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from fruitfly_agent.interactive import TerminalFrontend, EvaluationSnapshot, EvaluationBenchmarkOption, EvaluationVariantOption
from fruitfly_agent.interactive.contracts.improvement import ImprovementPreview, ImprovementTargetView, ImprovementMethodView, ImprovementParameterView
from fruitfly_agent.interactive.contracts.candidates import CandidateView
from fruitfly_agent.interactive.contracts.task_packs import TaskPackView
from fruitfly_agent.interactive.terminal.bindings import ImprovementClients
from fruitfly_agent.interactive.terminal.io.menu import MenuAction, MenuEvent
from tests.support.application import offline_session
from tests.support.terminal import ScriptedLines


def pick(index=0):
    return MenuEvent(MenuAction.ACTIVATE, index)

BACK = MenuEvent(MenuAction.BACK)
QUIT = MenuEvent(MenuAction.QUIT)


class ImprovementBackTests(unittest.IsolatedAsyncioTestCase):
    async def menu(self, events, *, clients=None, benchmark=None, reader=None, direction='improve'):
        clients = clients or ImprovementClients()
        if not clients.targets():
            clients = replace(clients, targets=lambda: (ImprovementTargetView('H', 'base_prompt', 'Base prompt'),))
        frontend = TerminalFrontend(offline_session(), input_stream=io.StringIO(), output_stream=io.StringIO(),
            improvement_clients=clients, evaluation=benchmark, line_editor=reader)
        frames, pending = [], list(events)
        def read():
            self.assertTrue(pending, 'Unexpected extra menu page')
            event = pending.pop(0)
            if isinstance(event, str):
                matches = [i for i, row in enumerate(frames[-1]['rows']) if row.label.startswith(event)]
                self.assertEqual(len(matches), 1, f'Expected one visible row {event!r}: {frames[-1]}')
                return pick(matches[0])
            return event
        frontend.menu_input = SimpleNamespace(read_event=read)
        frontend.menu_renderer = SimpleNamespace(ansi=False, render=lambda **frame: frames.append(frame),
            begin_input=lambda prompt, **options: frames.append({**frames[-1], **options, 'field': prompt}))
        result = await frontend.improvement_frontend().run((direction,) if direction else ())
        self.assertEqual(pending, [])
        return frames, result

    def services(self):
        search = SimpleNamespace(improvement_preview=Mock(return_value=ImprovementPreview(
            'method', 'Search', 'Costs', target='base_prompt', preview_token='token')), start_improvement=AsyncMock(return_value=()))
        benchmark = SimpleNamespace(improvement_available=True,
            improvement_snapshot=Mock(return_value=EvaluationSnapshot((EvaluationBenchmarkOption(
                'bench', 'Bench', 'Tasks', 'fixed', (EvaluationVariantOption('cpu', 'CPU', 'Five tasks', True),)),))),
            benchmark_preview=search.improvement_preview, improve=AsyncMock(return_value=()))
        return search, benchmark

    async def test_target_and_task_back_return_directly_to_panel(self):
        search, benchmark = self.services()
        frames, _ = await self.menu(['Target ·', BACK, 'Task ·', BACK, QUIT],
            clients=ImprovementClients(search=search), benchmark=benchmark)
        self.assertTrue(all(f['title']=='Improvement · Experiment' for f in frames))
        self.assertEqual([r.label.split(' · ')[0] for r in frames[0]['rows']],
            ['Target','Task','Budget','Evaluation','Start improvement','Results and history','Return to chat'])
        self.assertIn('Base prompt', [r.label for r in frames[1]['rows']])
        tasks=frames[3]['rows']
        self.assertTrue(any(r.label=='Configured task cases' and r.depth==1 for r in tasks))
        self.assertTrue(any(r.label=='Bench / CPU' and r.section=='Benchmark tasks' for r in tasks))
        self.assertEqual(frames[2]['selected'],0)
        search.start_improvement.assert_not_awaited()
        benchmark.improve.assert_not_awaited()

    async def test_confirmation_cancel_restores_selected_tasks_and_goal(self):
        search,benchmark=self.services()
        frames,result=await self.menu(['Target ·','Base prompt','Task ·','Bench / CPU',
            'Start improvement','Cancel',QUIT],clients=ImprovementClients(search=search),benchmark=benchmark)
        confirmation=next(f for f in frames if f['title']=='Confirm improvement')
        self.assertEqual(confirmation['selected'],1)
        self.assertIn('Search guidance: improve',confirmation['subtitle'])
        final=frames[-1]
        self.assertIn('Bench / CPU', next(r.label for r in final['rows'] if r.label.startswith('Task ·')))
        self.assertEqual(final['rows'][final['selected']].label,'Start improvement')
        self.assertIn('no task download or model calls',result)
        benchmark.improve.assert_not_awaited()

    async def test_quit_from_picker_exits_entire_panel(self):
        search,benchmark=self.services()
        frames,_=await self.menu(['Task ·',QUIT],clients=ImprovementClients(search=search),benchmark=benchmark)
        self.assertEqual(len(frames),2)
        self.assertTrue(all(f['title']=='Improvement · Experiment' for f in frames))
        search.start_improvement.assert_not_awaited()

    async def test_unique_saved_package_and_method_are_visible_without_picker(self):
        search,_=self.services()
        pack=TaskPackView('pack','Pack','hash',1,1,1,True,default_direction='Task default')
        clients=ImprovementClients(search=search, methods=lambda role,target:(
            ImprovementMethodView('method','Method','Search',default=True,direction_help='Optional guidance.'),),
            materials=SimpleNamespace(task_packs_available=True,task_packs=lambda:(pack,)))
        frames,_=await self.menu(['Target ·','Base prompt','Method',QUIT],clients=clients,direction='')
        self.assertIn('Pack',frames[0]['rows'][1].label)
        self.assertIn('Choose target',frames[0]['rows'][0].label)
        self.assertIn('Choose a compatible algorithm',frames[2]['subtitle'])
        self.assertEqual(frames[2]['rows'][frames[2]['selected']].label,'Method · suggested')
        self.assertNotIn('Choose algorithm',frames[-1]['rows'][0].label)
        search.improvement_preview.assert_called_once_with(pack_id='pack',direction='Task default',
            method_id='method',target_id='base_prompt')
        search.start_improvement.assert_not_awaited()

    async def test_goal_can_be_edited_without_losing_other_fields(self):
        search,_=self.services()
        frames,_=await self.menu(['Target ·','Base prompt','Search guidance',QUIT],
            clients=ImprovementClients(search=search),reader=ScriptedLines('New guidance'))
        self.assertTrue(any('New guidance' in r.label for r in frames[-1]['rows']))
        field=next(f for f in frames if 'field' in f)
        self.assertEqual(field['title'],'Improvement · Experiment')
        self.assertIn('Base prompt',field['rows'][0].label)
        self.assertIn('Current: improve',field['field'])
        search.start_improvement.assert_not_awaited()

    async def test_incompatible_target_requires_explicit_method_selection(self):
        search,_=self.services()
        search.improvement_preview.side_effect=lambda **kw:ImprovementPreview(kw['method_id'],'Method','Costs',
            target=kw['target_id'],role='I' if kw['target_id']=='policy' else 'H',preview_token='token')
        clients=ImprovementClients(search=search,targets=lambda:(ImprovementTargetView('H','base_prompt','Base prompt'),
            ImprovementTargetView('I','policy','Policy')),methods=lambda role,target:(
                ImprovementMethodView('method' if role=='H' else 'policy-method','Method','Search'),))
        frames,result=await self.menu(['Target ·','Base prompt','Method','Policy','Method',QUIT],clients=clients)
        self.assertIn('previous algorithm is incompatible',result)
        self.assertIn('Choose a compatible algorithm',frames[4]['subtitle'])
        self.assertEqual(search.improvement_preview.call_args.kwargs['method_id'],'policy-method')
        search.start_improvement.assert_not_awaited()

    async def test_unavailable_method_explains_reason_without_changing_selection(self):
        search,_=self.services()
        methods=(ImprovementMethodView('method','Default','Search',default=True),
            ImprovementMethodView('missing','Missing','',False,'Missing executor'))
        frames,result=await self.menu(['Target ·','Base prompt','Default','Missing',QUIT],
            clients=ImprovementClients(search=search,methods=lambda role,target:methods))
        self.assertIn('Missing executor',result)
        self.assertIn('Default',frames[-1]['rows'][0].label)
        unavailable=next(r for r in frames[-1]['rows'] if r.label=='Missing')
        self.assertEqual(unavailable.state,'unavailable')
        search.start_improvement.assert_not_awaited()

    async def test_budget_uses_declared_fields_and_rejects_out_of_range_values(self):
        search,_=self.services()
        spec=ImprovementParameterView('custom-budget','Request allowance','integer',20,1,30,'budget')
        clients=ImprovementClients(search=search,methods=lambda role,target:(
            ImprovementMethodView('method','Method','Search',parameters=(spec,)),))
        frames,result=await self.menu(['Target ·','Base prompt','Method','Budget ·','Request allowance',
            'Request allowance',QUIT],clients=clients,reader=ScriptedLines('100','8'))
        self.assertIn('Invalid parameter',result)
        self.assertTrue(any('Request allowance · 8' in r.label for r in frames[-1]['rows']))
        self.assertIn('Request allowance: 8',next(r.label for r in frames[-1]['rows'] if r.label.startswith('Budget ·')))
        self.assertEqual(search.improvement_preview.call_args.kwargs['parameters'],{'custom-budget':8})
        search.start_improvement.assert_not_awaited()

    async def test_budget_edit_repreviews_before_explicit_start(self):
        search,_=self.services()
        clients=ImprovementClients(search=search,methods=lambda role,target:(ImprovementMethodView(
            'method','Method','Search',direction_help='Optional guidance.', parameters=(
                ImprovementParameterView('limit','Request limit','integer',20,1,30,'budget'),)),))
        frames,result=await self.menu(['Target ·','Base prompt','Method','Budget ·','Request limit',
            'Start improvement','Start improvement',QUIT],clients=clients,reader=ScriptedLines('8'))
        search.start_improvement.assert_awaited_once_with('improve',preview_token='token')
        self.assertEqual(search.improvement_preview.call_args.kwargs['parameters'],{'limit':8})
        self.assertIn('Improvement completed',result)
        self.assertTrue(any(f['title']=='Improvement · Result · completed' for f in frames))

    async def test_no_compatible_methods_blocks_preview_and_start_without_host_fallback(self):
        search,_=self.services()
        frames,result=await self.menu(['Target ·','Base prompt','Start improvement',QUIT],
            clients=ImprovementClients(search=search, methods=lambda role,target:()))
        self.assertIn('No algorithm supports this target',result)
        self.assertIn('No compatible algorithm',frames[-1]['rows'][0].label)
        self.assertFalse(any(r.label.startswith('Search guidance') for f in frames for r in f['rows']))
        search.improvement_preview.assert_not_called()
        search.start_improvement.assert_not_awaited()

    async def test_algorithm_has_description_and_paths_without_internal_tuning_or_json(self):
        search,_=self.services()
        clients=ImprovementClients(search=search,methods=lambda role,target:(ImprovementMethodView(
            'method','Method','Generate candidates from scored history.', parameters=(
                ImprovementParameterView('rounds','Search rounds','integer',2,1,20),),
            implementation_path='example/method.py', documentation_path='example/README.md',
            configuration_path='/workspace/config.yaml', configuration_profile='daily'),))
        frames,_=await self.menu(['Target ·','Base prompt','Method',QUIT],clients=clients)
        self.assertFalse(any(r.label.startswith(('Search rounds', 'JSON overrides')) for f in frames for r in f['rows']))
        method=next(r for r in frames[-1]['rows'] if r.label=='Method')
        self.assertEqual(method.detail,'Generate candidates from scored history.')
        self.assertEqual(method.references,(('Implementation','example/method.py'),('Guide','example/README.md')))
        config=next(r for r in frames[-1]['rows'] if r.label=='Configuration location')
        self.assertIn('profiles.daily.mechanisms',config.detail)
        self.assertEqual(config.references,(('Configuration','/workspace/config.yaml'),))
        search.start_improvement.assert_not_awaited()

    async def test_method_without_guidance_shows_evaluation_and_sends_no_hidden_text(self):
        search,_=self.services()
        search.improvement_preview.return_value=ImprovementPreview('method','Method','Costs',
            (('Evaluation policy','fixed-score'),('Acceptance','Strict score gain')),'base_prompt','token')
        clients=ImprovementClients(search=search,methods=lambda role,target:(ImprovementMethodView('method','Method','Scores'),))
        frames,_=await self.menu(['Target ·','Base prompt','Method','Evaluation ·',
            'Start improvement','Start improvement',QUIT],clients=clients,direction='Old hidden guidance')
        self.assertFalse(any(r.label.startswith('Search guidance') for f in frames for r in f['rows']))
        self.assertTrue(any('fixed-score' in r.label for f in frames for r in f['rows']))
        self.assertTrue(any('Strict score gain' in r.detail for f in frames for r in f['rows']))
        self.assertNotIn('Old hidden guidance',next(f for f in frames if f['title']=='Confirm improvement')['subtitle'])
        search.start_improvement.assert_awaited_once_with('',preview_token='token')

    async def test_guidance_is_optional_and_can_be_cleared(self):
        search,_=self.services()
        clients=ImprovementClients(search=search,methods=lambda role,target:(ImprovementMethodView(
            'method','Method','Search',direction_help='Optional guidance.'),))
        frames,_=await self.menu(['Target ·','Base prompt','Method','Search guidance',
            'Start improvement','Start improvement',QUIT],clients=clients,reader=ScriptedLines('/clear'))
        self.assertTrue(any('(optional; not set)' in r.label for f in frames for r in f['rows']))
        search.start_improvement.assert_awaited_once_with('',preview_token='token')

    async def test_method_variables_have_individual_input_and_visible_values(self):
        search,_=self.services()
        specs=(ImprovementParameterView('history_path','History directory','path','old-path',group='materials',
            description='Read workspace-relative histories.'),ImprovementParameterView('rounds','Search rounds','integer',2,1,20,
            group='budget',description='Maximum proposal rounds.'))
        clients=ImprovementClients(search=search,methods=lambda role,target:(ImprovementMethodView(
            'method','Method','Search',parameters=specs),))
        frames,_=await self.menu(['Target ·','Base prompt','Method','Budget ·','Search rounds','Task ·','History directory',QUIT],
            clients=clients,reader=ScriptedLines('3','new-path'))
        fields=[f for f in frames if 'field' in f]
        self.assertIn('Type: integer',fields[0]['field'])
        self.assertIn('Maximum: 20',fields[0]['field'])
        self.assertIn('Current: old-path',fields[1]['field'])
        self.assertTrue(all(f['title']=='Improvement · Experiment' for f in fields))
        self.assertTrue(any('History directory · new-path' in r.label for r in frames[-1]['rows']))
        self.assertEqual(search.improvement_preview.call_args.kwargs['parameters'],{'history_path':'new-path','rounds':3})
        search.start_improvement.assert_not_awaited()

    async def test_variable_cancellation_and_invalid_input_keep_current_values(self):
        search,_=self.services()
        spec=ImprovementParameterView('rounds','Search rounds','integer',2,1,20,'budget')
        clients=ImprovementClients(search=search,methods=lambda role,target:(ImprovementMethodView(
            'method','Method','Search',parameters=(spec,)),))
        frames,result=await self.menu(['Target ·','Base prompt','Method','Budget ·','Search rounds','Search rounds',QUIT],
            clients=clients,reader=ScriptedLines('/cancel','21'))
        self.assertIn('Invalid parameter',result)
        self.assertTrue(any('Search rounds · 2' in r.label for r in frames[-1]['rows']))
        self.assertNotIn('parameters',search.improvement_preview.call_args.kwargs)
        search.start_improvement.assert_not_awaited()

    async def test_candidate_back_preserves_list_pagination(self):
        views=tuple(CandidateView(f'candidate-{i}','proposed','method','base_prompt','artifact','improve','parent') for i in range(12))
        candidates=SimpleNamespace(candidates=lambda:views,candidate_detail=Mock(return_value=(views[-1],'change')),candidate_action=Mock())
        frames,_=await self.menu(['Results and history',pick(),pick(10),pick(2),BACK,BACK,BACK,QUIT],
            clients=ImprovementClients(candidates=candidates))
        lists=[f for f in frames if f['title']=='Improvement candidates']
        self.assertIn('page 2/2',lists[-1]['subtitle'])
        self.assertEqual(lists[-1]['selected'],2)
        candidates.candidate_detail.assert_called_once_with('candidate-11')
        candidates.candidate_action.assert_not_called()

    async def test_material_capture_is_not_an_improvement_action(self):
        materials=SimpleNamespace(task_packs_available=True,task_packs=lambda:(),correction_tasks=Mock(),save_training_task=Mock())
        frames,_=await self.menu([BACK],clients=ImprovementClients(materials=materials))
        self.assertNotIn('Save a failed task',[r.label for f in frames for r in f['rows']])
        materials.correction_tasks.assert_not_called()
        materials.save_training_task.assert_not_called()

    async def test_target_change_retains_compatible_budget_and_requires_a_new_algorithm(self):
        search,_ = self.services()
        search.improvement_preview.side_effect = lambda **kw: ImprovementPreview(kw['method_id'], 'Method', 'Costs',
            target=kw['target_id'], role='I' if kw['target_id']=='policy' else 'H', preview_token='token')
        budget = ImprovementParameterView('allowance','Request allowance','integer',20,1,30,'budget')
        rounds = ImprovementParameterView('rounds','Search rounds','integer',2,1,20)
        clients = ImprovementClients(search=search, targets=lambda:(
            ImprovementTargetView('H','base_prompt','Base prompt'), ImprovementTargetView('I','policy','Policy')),
            methods=lambda role,target:(ImprovementMethodView('first' if role=='H' else 'second',
                'First' if role=='H' else 'Second', 'Search',parameters=(budget,rounds)),))
        frames,result = await self.menu(['Target ·','Base prompt','First','Budget ·','Request allowance',
            'Target ·','Policy','Second',QUIT],clients=clients,reader=ScriptedLines('7'))
        self.assertIn('previous algorithm is incompatible', result)
        self.assertEqual(search.improvement_preview.call_args.kwargs['parameters'], {'allowance':7})
        self.assertEqual(search.improvement_preview.call_args.kwargs['method_id'], 'second')
        self.assertFalse(any(r.label.startswith('Search rounds') for r in frames[-1]['rows']))
        search.start_improvement.assert_not_awaited()

    async def test_switching_target_rechecks_selected_task_projection_before_preview(self):
        search,_ = self.services()
        pack = TaskPackView('pack','Pack','hash',1,1,1,True)
        clients = ImprovementClients(search=search, targets=lambda:(
            ImprovementTargetView('H','base_prompt','Base prompt'), ImprovementTargetView('I','policy','Policy')),
            materials=SimpleNamespace(task_packs_available=True,task_packs=lambda:(pack,)),
            packs_for_target=lambda identity:(pack,) if identity=='base_prompt' else ())
        frames,_ = await self.menu(['Target ·','Base prompt','Policy','Start improvement',QUIT],clients=clients)
        self.assertIn('selected tasks are incompatible',frames[-1]['subtitle'])
        search.start_improvement.assert_not_awaited()

    async def test_switching_algorithms_discards_budget_overrides_with_changed_type_or_bounds(self):
        for changed in (ImprovementParameterView('allowance','Request allowance','path','default',group='budget'),
                        ImprovementParameterView('allowance','Request allowance','integer',2,1,3,'budget')):
            with self.subTest(kind=changed.kind):
                search,_=self.services()
                search.improvement_preview.side_effect=lambda **kw:ImprovementPreview(kw['method_id'],'Search','Costs',
                    target='base_prompt',preview_token='token')
                before=ImprovementParameterView('allowance','Request allowance','integer',20,1,30,'budget')
                clients=ImprovementClients(search=search,methods=lambda role,target:(
                    ImprovementMethodView('first','First','Scored history.',parameters=(before,)),
                    ImprovementMethodView('second','Second','Branch exploration.',parameters=(changed,))))
                _,result=await self.menu(['Target ·','Base prompt','First','Budget ·','Request allowance',
                    'Target ·','Second',QUIT],clients=clients,reader=ScriptedLines('7'))
                self.assertIn('compatible budget fields were reset',result)
                self.assertEqual(search.improvement_preview.call_args.kwargs['method_id'],'second')
                self.assertNotIn('parameters',search.improvement_preview.call_args.kwargs)
                search.start_improvement.assert_not_awaited()

    async def test_running_view_can_return_without_cancelling_owned_work(self):
        frontend=TerminalFrontend(offline_session(),input_stream=io.StringIO(),output_stream=io.StringIO())
        frames=[]
        frontend.menu_input=SimpleNamespace(poll_event=lambda timeout: pick())
        frontend.menu_renderer=SimpleNamespace(ansi=True,render=lambda **frame:frames.append(frame))
        view=frontend.improvement_frontend()
        task=asyncio.create_task(asyncio.Event().wait())
        try:
            self.assertTrue(await view.watch(task))
            self.assertFalse(task.done())
            self.assertEqual(frames[0]['title'],'Improvement · Running')
        finally:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)

    async def test_running_view_cancels_through_the_injected_application_operation(self):
        cancel=Mock(return_value=True)
        frontend=TerminalFrontend(offline_session(),input_stream=io.StringIO(),output_stream=io.StringIO(),
            improvement_clients=ImprovementClients(cancel=cancel))
        frontend.menu_input=SimpleNamespace(poll_event=lambda timeout: pick(1))
        frontend.menu_renderer=SimpleNamespace(ansi=True,render=lambda **frame:None)
        task=asyncio.create_task(asyncio.Event().wait())
        self.assertFalse(await frontend.improvement_frontend().watch(task))
        self.assertTrue(task.cancelled())
        cancel.assert_called_once()

    async def test_missing_benchmark_catalog_does_not_block_saved_task_selection(self):
        search,benchmark=self.services()
        benchmark.improvement_snapshot.side_effect=RuntimeError('Catalog unavailable')
        frames,result=await self.menu(['Task ·','Configured task cases',QUIT],
            clients=ImprovementClients(search=search),benchmark=benchmark)
        self.assertIn('Catalog unavailable',result)
        self.assertIn('Configured task cases',next(r.label for r in frames[-1]['rows'] if r.label.startswith('Task ·')))
        search.start_improvement.assert_not_awaited()
