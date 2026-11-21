"""Browser completion/cancellation and model paging have one terminal input owner."""
import io
import os
import threading
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock
from fruitfly_agent.interactive.terminal.features.configuration.model_connections import authorize, run_subscription_setup
from fruitfly_agent.interactive.terminal.features.configuration.model_picker import choose_subscription_model, _live_choice
from fruitfly_agent.interactive.terminal.io.menu import RawTerminalMenuInput
from fruitfly_agent.interactive.contracts.model_connections import ModelChoice

class ModelConnectionInterfaceTests(unittest.TestCase):
    def test_narrow_terminal_pagination_reaches_the_last_models(self):
        from fruitfly_agent.interactive.terminal.io.menu import MenuAction, MenuEvent
        from fruitfly_agent.interactive.terminal.features.configuration import model_picker

        rows = tuple(ModelChoice(f'model-{i}', f'Model {i}', 8192, 2048, True) for i in range(40))
        service = NS(models=lambda *_: rows, catalog_status=lambda *_: 'Cached')
        form = self.form(iter(()))
        form.renderer.ansi = False
        form.menu_input.poll_event = lambda _: MenuEvent(MenuAction.ACTIVATE, index=6)
        observed = []
        original = model_picker._live_choice

        def choose(*args, **kwargs):
            if len(observed) == 10:
                return False, model_picker.CANCELLED
            if len(observed) == 9:
                form.menu_input.poll_event = lambda _: MenuEvent(MenuAction.BACK)
                observed.append(kwargs['values'][0])
                return False, model_picker.CANCELLED
            result = original(*args, **kwargs)
            observed.append(result[1][1][0].id)
            return result

        with unittest.mock.patch.object(model_picker, '_live_choice', side_effect=choose), unittest.mock.patch.object(
            model_picker, 'terminal_size', return_value=os.terminal_size((70, 18))
        ):
            self.assertFalse(choose_subscription_model(form, service, 'fixture', 'account-a'))
        self.assertEqual(observed, [f'model-{i}' for i in range(0, 40, 4)])

    def test_picker_keeps_model_focus_when_resize_changes_page_capacity(self):
        rows = tuple(ModelChoice(f'model-{i}', f'模型 {i}', 8192, 2048, True) for i in range(40))
        service = NS(models=lambda *_: rows, catalog_status=lambda *_: 'Cached')
        form = self.form(iter((b'\x1b[B', b'\r')))
        form.renderer.ansi = True
        module = 'fruitfly_agent.interactive.terminal.features.configuration.model_picker'
        with unittest.mock.patch(module + '.terminal_size',
                side_effect=(os.terminal_size((100, 36)), os.terminal_size((70, 18)))):
            _, choice = _live_choice(form, service, 'fixture', 'account-a', '', 0)
        self.assertEqual(choice[0], 'model-1')
        self.assertIn('│', form.output.getvalue())
        self.assertIn('模型 26', form.output.getvalue())
        self.assertNotIn('模型 27', form.output.getvalue())
        narrow = form.renderer.render.call_args.kwargs
        self.assertEqual(narrow['rows'][narrow['selected']].label, '模型 1')
        self.assertIn('Maximum output: 2048', narrow['rows'][narrow['selected']].help.text)

    def form(self, events):
        return NS(menu_input=NS(poll_event=lambda timeout: RawTerminalMenuInput.decode(next(events))),
            renderer=NS(render=Mock()), input=io.StringIO(), output=io.StringIO(),
            apply=lambda function, *args: function(*args))

    def test_browser_callback_completes_automatically_without_reading_terminal(self):
        finished = threading.Event()
        attempt = NS(finished=finished, started=time.monotonic(), close=Mock())
        service = NS(begin_login=Mock(return_value=(attempt, 'https://auth.example/authorize', 'opaque-attempt')),
            open_browser=lambda url: finished.set(), complete_login=Mock(return_value='account-a'), cancel_login=Mock())
        form = self.form(iter(()))
        self.assertEqual(authorize(form, service, 'fixture'), 'account-a')
        service.complete_login.assert_called_once_with(attempt, 'opaque-attempt')
        attempt.close.assert_called_once()
        service.cancel_login.assert_called_once_with('opaque-attempt')

    def test_remote_browser_uses_hidden_callback_and_skips_local_browser(self):
        finished = threading.Event()
        attempt = NS(finished=finished, started=time.monotonic(), close=Mock(),
                     accept=Mock(side_effect=lambda _url: finished.set()))
        service = NS(begin_login=Mock(return_value=(attempt, 'https://auth.example/authorize', 'attempt')),
                     open_browser=Mock(), complete_login=Mock(return_value='account-a'), cancel_login=Mock())
        form = self.form(iter(()))
        with unittest.mock.patch(
            'fruitfly_agent.interactive.terminal.features.configuration.model_connections.read_secret',
            return_value='http://127.0.0.1:12345/auth/callback?code=hidden-fixture',
        ):
            self.assertEqual(authorize(form, service, 'fixture', remote_browser=True), 'account-a')
        service.open_browser.assert_not_called()
        attempt.accept.assert_called_once()
        self.assertIn('https://auth.example/authorize', form.output.getvalue())
        self.assertNotIn('hidden-fixture', form.output.getvalue())

    def test_cancel_closes_pending_authorization_without_completing_or_staging(self):
        attempt = NS(finished=threading.Event(), started=time.monotonic(), close=Mock())
        service = NS(begin_login=Mock(return_value=(attempt, 'https://auth.example/authorize', 'opaque-attempt')),
            open_browser=Mock(), complete_login=Mock(), cancel_login=Mock())
        form = self.form(iter((b'q',)))
        self.assertIsNone(authorize(form, service, 'fixture'))
        service.complete_login.assert_not_called()
        attempt.close.assert_called_once()

    def test_authorization_back_revisits_storage_then_accounts(self):
        from fruitfly_agent.interactive.terminal.features.configuration.forms import CANCELLED
        seen = []
        steps = iter(('new', 'file', 'Back', CANCELLED, CANCELLED))

        def choose(**kwargs):
            seen.append(kwargs['title'])
            return False, next(steps)

        option = NS(id='fixture', label='Fixture', method='key', url='https://fixture.invalid')
        service = NS(options=lambda: (option,), accounts=lambda: (), choose_storage=Mock(), connect_key=Mock())
        self.assertFalse(run_subscription_setup(NS(choose_value=choose), service, 'fixture'))
        self.assertEqual(seen, ['Fixture · Account', 'Credential storage', 'Fixture',
                                'Credential storage', 'Fixture · Account'])
        service.connect_key.assert_not_called()

    def test_model_search_paging_and_cancellation_do_not_stage_models(self):
        rows = tuple(ModelChoice(f'model-{i}', f'Model {i}', 8192, 2048, True) for i in range(20))
        selected = []
        def choose(**kwargs):
            selected.append(kwargs['title'])
            if len(selected) == 1:
                self.assertEqual(len([v for v in kwargs['values'] if v.startswith('model-')]), 8)
                return False, 'Next page'
            self.assertIn('2/3', kwargs['title'])
            return False, 'Back'
        form = NS(menu_input=NS(), choose_value=choose)
        service = NS(models=Mock(return_value=rows), catalog_status=Mock(return_value='Cached'), stage=Mock())
        choose_subscription_model(form, service, 'fixture', 'account-a')
        service.stage.assert_not_called()

    def test_escape_at_model_label_cancels_without_staging(self):
        from unittest.mock import patch
        from fruitfly_agent.interactive.terminal.io.controls import InputInterrupted, InputEnded
        module = 'fruitfly_agent.interactive.terminal.features.configuration.model_picker'
        model = ModelChoice('fixture-model', 'Fixture model', 8192, 2048, True)
        service = NS(models=lambda *_: (model,), catalog_status=lambda *_: 'Cached', stage=Mock())
        for interruption in (InputInterrupted, KeyboardInterrupt, InputEnded):
            with self.subTest(interruption=interruption):
                form = NS(line_editor=Mock(), menu_input=NS(), choose_value=Mock(side_effect=[(False, model.id), (False, 'Use model')]))
                with patch(module + '.read_field_line', side_effect=interruption):
                    if interruption is InputEnded:
                        with self.assertRaises(InputEnded):
                            choose_subscription_model(form, service, 'fixture', 'account')
                    else:
                        self.assertFalse(choose_subscription_model(form, service, 'fixture', 'account'))
                service.stage.assert_not_called()

    def test_authorization_interrupt_is_cancellation_and_always_closes(self):
        from fruitfly_agent.interactive.terminal.io.controls import InputInterrupted, InputEnded
        for interruption in (InputInterrupted, KeyboardInterrupt, InputEnded):
            with self.subTest(interruption=interruption):
                attempt = NS(finished=threading.Event(), started=time.monotonic(), close=Mock())
                service = NS(begin_login=Mock(return_value=(attempt, 'https://example.invalid', 'record')),
                    open_browser=Mock(), complete_login=Mock(), cancel_login=Mock())
                form = self.form(iter(()))
                form.menu_input.poll_event = Mock(side_effect=interruption)
                form.apply = Mock()
                if interruption is InputEnded:
                    with self.assertRaises(InputEnded):
                        authorize(form, service, 'fixture')
                else:
                    self.assertIsNone(authorize(form, service, 'fixture'))
                form.apply.assert_not_called()
                service.complete_login.assert_not_called()
                attempt.close.assert_called_once()
                service.cancel_login.assert_called_once_with('record')
