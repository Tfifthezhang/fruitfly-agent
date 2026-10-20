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

    def _form_values(self, mechanism_id, inputs=None, profile=None):
        definition = self.catalog.get(mechanism_id)
        setup = definition.setup
        if setup is None:
            raise ValueError('This mechanism has no setup form')
        values = self.parameters(mechanism_id, profile)
        fields = {p.name: p for p in definition.descriptor.parameters}
        if inputs is not None:
            if set(inputs) - set(setup.fields):
                raise ValueError('Unknown setup field')
            values.update({name: fields[name].parse(value) for name, value in inputs.items()})
        if definition.validate_parameters is not None:
            definition.validate_parameters(values)
        return definition, values, fields

    def form(self, mechanism_id, values=None):
        definition, parameters, fields = self._form_values(mechanism_id, values)
        setup = definition.setup
        credentials = definition.setup_credentials(parameters)
        return ConfigurationSetup(mechanism_id, definition.descriptor.label,
            tuple(ConfigurationParameter(name, fields[name].label, fields[name].description,
                fields[name].kind, parameters[name], choices=fields[name].choices,
                minimum=fields[name].minimum, maximum=fields[name].maximum) for name in setup.fields),
            tuple(ConfigurationCredential(c.parameter, c.label, c.description,
                self.credentials.available(c.variable or parameters[c.parameter])) for c in credentials), setup.guidance)

    def validate_field(self, mechanism_id, name, value, values=None):
        definition, parameters, _ = self._form_values(mechanism_id, {**(values or {}), name: value})
        if name in definition.setup.required_fields and not str(parameters[name]).strip():
            raise ValueError(f'{name} is required')

    def _check_credential(self, field, parameters, value):
        if not field.allow_whitespace and any(char.isspace() for char in value):
            raise ValueError('API key must contain no whitespace')
        variable = field.variable or parameters[field.parameter]
        self.credentials.check(variable, value)
        return variable

    def validate_credential(self, mechanism_id, name, value, values=None):
        definition, parameters, _ = self._form_values(mechanism_id, values)
        field = next((c for c in definition.setup_credentials(parameters) if c.parameter == name), None)
        if field is None:
            raise ValueError('Unknown credential input')
        self._check_credential(field, parameters, value)

    def issues(self, mechanism_id, profile=None):
        definition = self.catalog.get(mechanism_id)
        if definition.setup is None:
            return ()
        definition, values, fields = self._form_values(mechanism_id, profile=profile)
        missing = [fields[name].label for name in definition.setup.required_fields if not str(values[name]).strip()]
        missing.extend(c.label for c in definition.setup_credentials(values)
                       if not self.credentials.available(c.variable or values[c.parameter]))
        return tuple(missing)

    def ready(self, mechanism_id):
        return not self.issues(mechanism_id)

    def credential_status(self, mechanism_id):
        definition = self.catalog.get(mechanism_id)
        return tuple((name, self.credentials.available(name))
                     for name in definition.required_credentials(self.parameters(mechanism_id)))

    def stage(self, mechanism_id, values, secrets):
        definition, parameters, _ = self._form_values(mechanism_id, values)
        setup = definition.setup
        fields = definition.setup_credentials(parameters)
        if set(secrets) - {c.parameter for c in fields}:
            raise ValueError('Unknown credential input')
        if any(not str(parameters[name]).strip() for name in setup.required_fields):
            raise ValueError('Required setup information is missing')
        additions: dict[str, str] = {}
        for field in fields:
            value = secrets.get(field.parameter, '')
            variable = self._check_credential(field, parameters, value)
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
