"""Editable evaluation prompts; evidence authority and output validation stay in code."""
from fruitfly_agent.runtime_spec.documents import parameter_default
from dataclasses import asdict, dataclass, field
import json
from .configuration import EvaluatorSettings
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec, OptimizationField, TargetSnapshot, TargetBinding
from fruitfly_agent.improvement.contracts.versions import canonical_json


@dataclass(frozen=True)
class EvaluatorInstructions:
    criteria: str = (
        field(default_factory=lambda: parameter_default(__package__ + '.methods.model', 'defaults.yaml', 'instructions.criteria')))
    assess: str = (
        field(default_factory=lambda: parameter_default(__package__ + '.methods.model', 'defaults.yaml', 'instructions.assess')))
    compare: str = (
        field(default_factory=lambda: parameter_default(__package__ + '.methods.model', 'defaults.yaml', 'instructions.compare')))

    system: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.model', 'defaults.yaml', 'instructions.system'))
    schema: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.model', 'defaults.yaml', 'instructions.schema'))
    coverage: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.model', 'defaults.yaml', 'instructions.coverage'))
    submit: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.model', 'defaults.yaml', 'instructions.submit'))
    catalog: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.model', 'defaults.yaml', 'instructions.catalog'))
    submit_judgment: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.model', 'defaults.yaml', 'instructions.submit_judgment'))

    def __post_init__(self):
        for value in asdict(self).values():
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 16000:
                raise ValueError('evaluator instructions must contain 1..16000 characters')


class EvaluatorInstructionTarget:
    structured_parameters = True
    optimization = OptimizationSpec('I', 'parameters', required_capabilities=frozenset({'improver-comparison'}), default_selected=False)
    component_kind = 'evaluator-instructions'
    required_capabilities = frozenset({'improver-comparison'})
    adoption_roles = frozenset({'I'})
    label = 'Improvement evaluator'

    def __init__(self, instructions=None, *, text=None, settings=None):
        self.instructions = instructions or EvaluatorInstructions()
        self.settings = EvaluatorSettings.from_dict(settings)
        self.text = canonical_json({'instructions': asdict(self.instructions), 'settings': asdict(self.settings)}) if text is None else text
        if self.parse(self.text) != self.instructions or EvaluatorSettings.from_dict(json.loads(self.text)['settings']) != self.settings:
            raise ValueError('evaluator source differs from installed instructions')

    def snapshot(self):
        return TargetSnapshot('improvement-evaluator', self.text,
            TargetBinding('artifact', 'improvement-evaluator'), 'evaluator-instructions-v1', 'I')

    def describe_fields(self, text=None):
        instructions = self.instructions if text is None else self.parse(text)
        descriptions = {'criteria': 'Define what task outcomes and dimensions to evaluate from the original requirements.',
            'assess': 'Explain how to judge one execution, including per-dimension reasons, uncertainty, and observed evidence.',
            'compare': 'Compare executed alternatives using common criteria; resolve tradeoffs or retain an uncertain incumbent.'}
        return tuple(OptimizationField('parameters.instructions.' + key, 'string', descriptions.get(key, 'Configure ' + key.replace('_', ' ') + ' guidance.'), value,
            getattr(EvaluatorInstructions(), key), unit='characters', minimum=1, maximum=16000)
            for key, value in asdict(instructions).items())

    @staticmethod
    def parse(text):
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError('duplicate evaluator field')
                value[key] = item
            return value
        value = json.loads(text, object_pairs_hook=unique)
        if not isinstance(value, dict) or set(value) != {'instructions', 'settings'} or set(value['instructions']) != set(EvaluatorInstructions.__dataclass_fields__):
            raise ValueError('evaluator requires exactly its instruction fields')
        EvaluatorSettings.from_dict(value['settings'])
        return EvaluatorInstructions(**value['instructions'])

    def validate(self, text):
        self.parse(text)
        if EvaluatorSettings.from_dict(json.loads(text)['settings']) != self.settings:
            raise ValueError('candidate changed protected role settings')

    def validate_options(self, options):
        allowed = {'parameters.instructions.' + key for key in EvaluatorInstructions.__dataclass_fields__}
        if not isinstance(options, dict) or set(options) - {'editable_fields', 'bounds'} or options.get('bounds'):
            raise ValueError('evaluator grants accept prompt fields without numeric bounds')
        fields = options.get('editable_fields', sorted(allowed))
        if not isinstance(fields, list) or not fields or len(set(fields)) != len(fields) or set(fields) - allowed:
            raise ValueError('invalid evaluator prompt grant')

    def validate_change(self, text, options):
        self.validate(text)
        value = self.parse(text)
        allowed = set(options.get('editable_fields', ('parameters.instructions.' + key for key in asdict(self.instructions))))
        for key, before in asdict(self.instructions).items():
            if 'parameters.instructions.' + key not in allowed and getattr(value, key) != before:
                raise ValueError('candidate changed a fixed evaluator prompt')

    def prepare_trial(self, config, text):
        raise ValueError('evaluator changes require an independently measured fixed-I comparison')
