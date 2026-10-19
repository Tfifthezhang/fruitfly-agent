"""Guided registration-driven setup with hidden credential inputs."""
from fruitfly_agent.interactive.contracts.mechanism_setup import MechanismSetupService
from fruitfly_agent.interactive.terminal.io.input import read_field_line
from fruitfly_agent.interactive.terminal.io.live import InputInterrupted
from .model_setup import ModelFormIO, read_secret


def run_mechanism_setup(form: ModelFormIO, service: MechanismSetupService, mechanism_id: str) -> bool:
    setup = service.form(mechanism_id)
    values: dict[str, str] = {}
    secrets: dict[str, str] = {}
    total = len(setup.fields) + len(setup.credentials)
    def render(step, label, description, hint, notice=''):
        form.renderer.render(title=f'Set up {setup.label} · Step {step} of {total}',
            subtitle=f'{label}\n{description}\n{hint}\n\n{setup.guidance}', rows=(), selected=0,
            notice=notice, instructions='Enter to continue · /cancel to return without changes. Nothing is saved yet.')
    try:
        for step, field in enumerate(setup.fields, 1):
            default = str(field.value if field.value is not None else '')
            notice = ''
            while True:
                render(step, field.label, field.description, f'Press Enter to use: {default}' if default else 'Required field.', notice)
                line = read_field_line(form.line_editor, field.label)
                if line is None or line.strip() == '/cancel':
                    return False
                value = line.strip() or default
                try:
                    service.validate_field(mechanism_id, field.name, value)
                except (TypeError, ValueError) as exc:
                    notice = f'Invalid {field.label}: {exc}'
                    continue
                values[field.name] = value
                break
        for step, field in enumerate(setup.credentials, len(setup.fields) + 1):
            notice = ''
            while True:
                hint = ('Already set; press Enter to reuse the existing value.' if field.available
                        else 'Missing; enter a value to continue.')
                render(step, field.label, field.description, hint, notice)
                secret = read_secret(form.input, form.output,
                    prompt=f'{field.label} (hidden; blank reuses an existing value): ')
                if secret is None or secret == '/cancel':
                    return False
                try:
                    service.validate_credential(mechanism_id, field.parameter, secret)
                except (TypeError, ValueError):
                    notice = f'{field.label} is missing or conflicts with an existing secret variable. '
                    notice += 'Enter a valid value, reuse the existing value, or cancel to change the variable in configuration.'
                    continue
                secrets[field.parameter] = secret
                break
        quit_requested, action = form.choose_value(
            title=f'Set up {setup.label} · Review',
            subtitle='\n'.join(f'{field.label}: {values[field.name]}' for field in setup.fields) + '\n' +
                '\n'.join(f'{field.label}: ' + ('entered' if secrets[field.parameter] else 'reused') + ' (value hidden)'
                          for field in setup.credentials) +
                '\nOffline checks only. Settings and credentials remain staged until configuration is saved.',
            values=('Cancel', 'Stage settings'), current='Cancel')
        if quit_requested or action != 'Stage settings':
            return False
        return form.apply(service.stage, mechanism_id, values, secrets) is not None
    except (InputInterrupted, KeyboardInterrupt):
        return False
