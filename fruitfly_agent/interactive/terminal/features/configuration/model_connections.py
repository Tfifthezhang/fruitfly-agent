"""Account connection screens driven solely by injected host capabilities."""
from __future__ import annotations
import time
from fruitfly_agent.interactive.terminal.io.controls import InputEnded, InputInterrupted
from typing import Any
from fruitfly_agent.interactive.terminal.io.controls import cancellable_form
from .forms import CANCELLED
from ..configuration.model_picker import choose_subscription_model
from fruitfly_agent.interactive.terminal.io.secret import read_secret
from fruitfly_agent.interactive.terminal.io.input import read_field_line
from fruitfly_agent.interactive.terminal.io.menu import MenuAction, MenuRow, navigate_menu


def _storage(form: Any, service: Any) -> bool:
    while True:
        _, backend = form.choose_value(title='Credential storage',
            subtitle='System storage protects account tokens. Protected files use owner-only local permissions. No model request is sent.',
            values=('keyring', 'file'), current='keyring',
            labels={'keyring': 'System credential store (recommended)', 'file': 'Protected local files'})
        if backend is CANCELLED:
            return False
        try:
            service.choose_storage(backend)
            return True
        except (ValueError, OSError) as exc:
            form.apply(lambda: _message(str(exc)))


def _message(text: str) -> Any:
    from fruitfly_agent.interactive.contracts.configuration import ConfigurationActionResult
    return ConfigurationActionResult(text)


def authorize(form: Any, service: Any, integration: str, account: str = '', *, remote_browser: bool = False) -> str | None:
    try:
        attempt, url, record = service.begin_login(integration, account)
    except (ValueError, OSError) as exc:
        form.apply(lambda: _message(str(exc)))
        return None
    selected = 0
    try:
        if remote_browser:
            form.output.write('Open this link in your browser. After consent, copy the full callback '
                              'URL from the address bar, even if the page cannot load.\n'
                              + url + '\n')
            form.output.flush()
            callback = read_secret(form.input, form.output, prompt='Callback URL (hidden; /cancel returns): ')
            if not callback or callback == '/cancel':
                return None
            attempt.accept(callback)
        else:
            service.open_browser(url)
        while not attempt.finished.is_set():
            if time.monotonic() - attempt.started > 300:
                form.apply(lambda: _message('Authorization timed out; try again.'))
                return None
            poll = getattr(form.menu_input, 'poll_event', None)
            if poll is None:
                _, action = form.choose_value(title='Waiting for authorization',
                    subtitle='Complete sign-in in your browser.\n' + url,
                    values=('Continue', 'Open browser again', 'Use callback link…', 'Cancel'), current='Continue')
                if action is CANCELLED or action == 'Cancel':
                    return None
            else:
                actions = ('Open browser again', 'Use callback link…', 'Cancel')
                form.renderer.render(title='Waiting for authorization',
                    subtitle='Complete sign-in in your browser. Return here automatically after authorization.\n' + url,
                    rows=tuple(MenuRow(v) for v in actions), selected=selected,
                    instructions='↑↓ move · Enter select · Esc cancel')
                event = poll(.15)
                if event.action in (MenuAction.BACK, MenuAction.QUIT):
                    return None
                selected, handled = navigate_menu(event, selected, len(actions))
                if handled or event.action != MenuAction.ACTIVATE:
                    continue
                action = actions[selected]
            if action == 'Cancel':
                return None
            if action == 'Open browser again':
                service.open_browser(url)
            if action == 'Use callback link…':
                callback = read_secret(form.input, form.output, prompt='Final callback URL (hidden; /cancel returns): ')
                if callback and callback != '/cancel':
                    try:
                        attempt.accept(callback)
                    except ValueError as exc:
                        form.apply(lambda: _message(str(exc)))
        result = service.complete_login(attempt, record)
        form.apply(lambda: _message('Account connected. Choose a model to use it.'))
        return result
    except (InputInterrupted, KeyboardInterrupt):
        return None
    except InputEnded:
        raise
    except Exception as exc:
        form.apply(lambda: _message('Authorization failed; account and model selection retained. ' + type(exc).__name__))
        return None
    finally:
        attempt.close()
        service.cancel_login(record)


def _connect_account(form: Any, service: Any, option: Any, account: str) -> str | None:
    while _storage(form, service):
        while True:
            actions = (('Open account console', 'Paste subscription key') if option.method == 'key'
                       else (option.action_label, 'Authorize in another browser…'))
            _, action = form.choose_value(title=option.label,
                subtitle='Back returns to credential storage.',
                values=actions + ('Back',), current=actions[1] if option.method == 'key' else actions[0])
            if action is CANCELLED or action == 'Back':
                break
            if action == 'Open account console':
                service.open_browser(option.url)
                continue
            if option.method == 'key':
                key = read_secret(form.input, form.output, prompt='Subscription key (hidden; /cancel returns): ')
                if not key or key == '/cancel':
                    continue
                try:
                    return service.connect_key(option.id, key, option.label, account)
                except (ValueError, OSError) as exc:
                    form.apply(lambda: _message(str(exc)))
            else:
                authorized = authorize(form, service, option.id, account,
                                       remote_browser=action == 'Authorize in another browser…')
                if authorized is not None:
                    return authorized
    return None


@cancellable_form
def run_subscription_setup(form: Any, service: Any, integration: str, saved_account: str = '') -> bool:
    option = next(item for item in service.options() if item.id == integration)
    while True:
        accounts = tuple(item for item in service.accounts() if item.integration == integration)
        account = saved_account
        if not account:
            variable_source = option.method == 'key' and hasattr(service, 'use_key_variable')
            _, chosen = form.choose_value(title=option.label + ' · Account',
                subtitle='Choose a saved account or connect another. Back returns to providers.',
                values=tuple(a.id for a in accounts) + ('new',) + (('variable',) if variable_source else ()),
                current=accounts[0].id if accounts else 'new',
                labels={**{a.id: a.label + ' · ' + a.status for a in accounts}, 'new': 'Connect another account…',
                        'variable': 'Use a key variable from secrets.env…'})
            if chosen is CANCELLED:
                return False
            if chosen == 'variable':
                name = read_field_line(form.line_editor, 'Subscription key variable name')
                if not name or name == '/cancel':
                    continue
                try:
                    account = service.use_key_variable(integration, name.strip())
                except ValueError as exc:
                    form.apply(lambda: _message(str(exc)))
                    continue
                if choose_subscription_model(form, service, integration, account):
                    return True
                continue
            account = '' if chosen == 'new' else chosen
        connected = any(a.id == account and a.status == 'connected' for a in accounts)
        if not connected:
            account = _connect_account(form, service, option, account)
            if account is None:
                if saved_account:
                    return False
                continue
        if choose_subscription_model(form, service, integration, account):
            return True
        if saved_account:
            return False


@cancellable_form
def manage_connections(form: Any, service: Any) -> None:
    while True:
        accounts = service.accounts()
        options = service.options()
        values = tuple(a.id for a in accounts) + tuple('add:' + o.id for o in options) + ('back',)
        labels = {**{a.id: a.label + ' · ' + a.integration + ' · ' + a.status for a in accounts},
                  **{'add:' + o.id: 'Connect ' + o.label + '…' for o in options}, 'back': 'Back'}
        _, action = form.choose_value(title='Connections', subtitle='Accounts are independent of the current model configuration.',
            values=values, current='back', labels=labels)
        if action is CANCELLED or action == 'back':
            return
        if action.startswith('add:'):
            run_subscription_setup(form, service, action[4:])
            continue
        account = next(a for a in accounts if a.id == action)
        _, choice = form.choose_value(title=account.label,
            subtitle='Project connections: ' + (', '.join(account.references) or 'None in this project'),
            values=('Choose model…', 'Reauthorize…', 'Rename…', 'Sign out…', 'Back'), current='Choose model…')
        if choice == 'Choose model…':
            run_subscription_setup(form, service, account.integration, account.id)
        elif choice == 'Reauthorize…':
            option = next(o for o in options if o.id == account.integration)
            _connect_account(form, service, option, account.id)
        elif choice == 'Rename…':
            label = read_field_line(form.line_editor, 'Account name')
            if label and label != '/cancel':
                form.apply(service.rename, account.id, label)
        elif choice == 'Sign out…':
            _, confirm = form.choose_value(title='Sign out',
                subtitle='This stops subsequent requests using this account. Saved model configuration remains.',
                values=('Cancel', 'Sign out'), current='Cancel')
            if confirm == 'Sign out':
                try:
                    confirmed = service.logout(account.id)
                    form.apply(lambda: _message('Signed out.' if confirmed else 'Signed out locally. Remote revocation was not confirmed; disconnect the app or revoke its key in the service console.'))
                except (ValueError, OSError):
                    form.apply(lambda: _message('Sign-out failed; account state retained.'))


@cancellable_form
def advanced_model_settings(form: Any, service: Any, alias: str) -> None:
    import json
    try:
        current = service.parameters(alias)
        line = read_field_line(form.line_editor, 'Request options [' + json.dumps(current) + ']')
        if line is None or line == '/cancel':
            return
        value = json.loads(line) if line.strip() else current
        _, action = form.choose_value(title='Review request options', subtitle=json.dumps(value, indent=2),
            values=('Cancel', 'Stage options'), current='Cancel')
        if action == 'Stage options':
            form.apply(service.edit_parameters, alias, value)
    except (ValueError, TypeError, KeyError) as exc:
        form.apply(lambda: _message(str(exc)))
