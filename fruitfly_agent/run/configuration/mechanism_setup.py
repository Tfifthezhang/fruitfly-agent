"""Registration-driven mechanism setup; no backend-specific host branches."""
from dataclasses import replace

from fruitfly_agent.interactive.contracts.configuration import ConfigurationActionResult, ConfigurationParameter
from fruitfly_agent.interactive.contracts.mechanism_setup import ConfigurationCredential, ConfigurationSetup
from fruitfly_agent.lab.catalog import MechanismSelection


class RunMechanismSetup:
    def __init__(self, *, catalog, current_profile, stage_profile, enable, credentials):
        self.catalog = catalog
        self.current_profile = current_profile
        self.stage_profile = stage_profile
        self.enable = enable
        self.credentials = credentials

    def parameters(self, mechanism_id, profile=None):
        profile = profile or self.current_profile()
        selection = next((item for item in profile.mechanisms if item.mechanism_id == mechanism_id), None)
        return self.catalog.get(mechanism_id).descriptor.normalize_parameters(selection.parameters if selection else {})

    def form(self, mechanism_id):
        definition = self.catalog.get(mechanism_id)
        setup = definition.setup
        if setup is None:
            raise ValueError('This mechanism has no setup form')
        values = self.parameters(mechanism_id)
        fields = {p.name: p for p in definition.descriptor.parameters}
        return ConfigurationSetup(mechanism_id, definition.descriptor.label,
            tuple(ConfigurationParameter(name, fields[name].label, fields[name].description,
                fields[name].kind, values[name], choices=fields[name].choices,
                minimum=fields[name].minimum, maximum=fields[name].maximum) for name in setup.fields),
            tuple(ConfigurationCredential(c.parameter, c.label, c.description,
                self.credentials.available(values[c.parameter])) for c in setup.credentials), setup.guidance)

    def validate_field(self, mechanism_id, name, value):
        definition = self.catalog.get(mechanism_id)
        setup = definition.setup
        if setup is None or name not in setup.fields:
            raise ValueError('Unknown setup field')
        descriptor = next(p for p in definition.descriptor.parameters if p.name == name)
        parsed = descriptor.parse(value)
        if name in setup.required_fields and not str(parsed).strip():
            raise ValueError(f'{descriptor.label} is required')
        values = {**self.parameters(mechanism_id), name: parsed}
        if definition.validate_parameters is not None:
            definition.validate_parameters(values)

    def validate_credential(self, mechanism_id, name, value):
        definition = self.catalog.get(mechanism_id)
        if definition.setup is None or name not in {c.parameter for c in definition.setup.credentials}:
            raise ValueError('Unknown credential input')
        self.credentials.check(self.parameters(mechanism_id)[name], value)

    def issues(self, mechanism_id, profile=None):
        definition = self.catalog.get(mechanism_id)
        setup = definition.setup
        if setup is None:
            return ()
        values = self.parameters(mechanism_id, profile)
        labels = {p.name: p.label for p in definition.descriptor.parameters}
        missing = [labels[name] for name in setup.required_fields if not str(values[name]).strip()]
        missing.extend(c.label for c in setup.credentials if not self.credentials.available(values[c.parameter]))
        return tuple(missing)

    def ready(self, mechanism_id):
        return not self.issues(mechanism_id)

    def stage(self, mechanism_id, values, secrets):
        definition = self.catalog.get(mechanism_id)
        setup = definition.setup
        if setup is None:
            raise ValueError('This mechanism has no setup form')
        if set(values) - set(setup.fields) or set(secrets) - {c.parameter for c in setup.credentials}:
            raise ValueError('Unknown setup input')
        parameters = self.parameters(mechanism_id)
        for name, value in values.items():
            self.validate_field(mechanism_id, name, value)
            descriptor = next(p for p in definition.descriptor.parameters if p.name == name)
            parameters[name] = descriptor.parse(value)
        for name in setup.required_fields:
            if not str(parameters[name]).strip():
                raise ValueError('Required setup information is missing')
        if definition.validate_parameters is not None:
            definition.validate_parameters(parameters)
        additions = {}
        for field in setup.credentials:
            value = secrets.get(field.parameter, '')
            variable = parameters[field.parameter]
            self.credentials.check(variable, value)
            if value:
                if variable in additions and additions[variable] != value:
                    raise ValueError('Credential inputs require distinct secret variables')
                additions[variable] = value
        # Stage configuration and resolve conflicts as one reversible operation.
        original = self.current_profile()
        selected = {item.mechanism_id: item for item in original.mechanisms}
        selected[mechanism_id] = MechanismSelection(mechanism_id, False, parameters)
        try:
            self.stage_profile(replace(original, mechanisms=tuple(selected.values())))
            self.enable(mechanism_id, enabled=True)
            self.catalog.resolve(self.current_profile().mechanisms)
        except BaseException:
            self.stage_profile(original)
            raise
        self.credentials.values.update(additions)
        return ConfigurationActionResult('Settings and hidden credentials staged; save to use in a new session', changed=True)
