"""Editable evaluation prompts; evidence authority and output validation stay in code."""
from dataclasses import asdict, dataclass
import json
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec, OptimizationField, TargetSnapshot, TargetBinding
from fruitfly_agent.improvement.contracts.versions import canonical_json


@dataclass(frozen=True)
class EvaluatorInstructions:
    criteria: str = (
        'Derive concrete task-specific criteria for these dimensions when applicable: '
        'task quality (correctness, completeness and constraints); execution reliability (failures, repeated errors and recovery); '
        'resource efficiency (reported tokens, cache, model/tool/wait time); progress efficiency (useful steps, repetition and rework); '
        'verification and evidence quality (valid checks, hidden command failures, source support); '
        'completion efficiency (value of actions after sufficient completion evidence). '
        'A saturated outcome score still permits process improvement. Action counts alone are not quality. '
        'Distinguish installed candidate changes from observed behavioral improvements. Missing facts are unknown.')
    assess: str = (
        'Inspect the overview and event catalog, then search and read relevant original spans. '
        'Judge each applicable dimension with reasons, uncertainty and precise citations. '
        'A successful tool status does not establish success of every enclosed command. '
        'Explain observed process signals and concrete next modification hypotheses, including evidence that would refute them. '
        'Check supplied expected effects against behavior; do not infer causation from one run. '
        'Distinguish infrastructure failures from task failures. Do not invent a total numeric score or unreported cost.')
    compare: str = (
        'Compare existing runs with identical dimensions and criteria. Respect official measurements and fixed regression requirements. '
        'Prioritize task quality and reliability before efficiency. When quality is supported as equal, consider resource, progress and '
        'completion efficiency with uncertainty. Fewer model calls do not establish lower token use or elapsed time. '
        'Explain tradeoffs, hypothesis outcomes and next optimization directions with source citations. '
        'Retain the incumbent or report no clear choice when evidence is insufficient. Selection does not grant independent adoption.')

    def __post_init__(self):
        for value in asdict(self).values():
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 16000:
                raise ValueError('evaluator instructions must contain 1..16000 characters')


class EvaluatorInstructionTarget:
    optimization = OptimizationSpec('I', 'parameters', required_capabilities=frozenset({'improver-comparison'}))
    component_kind = 'evaluator-instructions'
    required_capabilities = frozenset({'improver-comparison'})
    adoption_roles = frozenset({'I'})
    label = 'Improvement evaluator'

    def __init__(self, instructions=None, *, text=None):
        self.instructions = instructions or EvaluatorInstructions()
        self.text = canonical_json({'instructions': asdict(self.instructions)}) if text is None else text
        if self.parse(self.text) != self.instructions:
            raise ValueError('evaluator source differs from installed instructions')

    def snapshot(self):
        return TargetSnapshot('improvement-evaluator', self.text,
            TargetBinding('artifact', 'improvement-evaluator'), 'evaluator-instructions-v1', 'I')

    def describe_fields(self, text=None):
        instructions = self.instructions if text is None else self.parse(text)
        descriptions = {'criteria': 'Define what task outcomes and dimensions to evaluate from the original requirements.',
            'assess': 'Explain how to judge one execution, including per-dimension reasons, uncertainty, and observed evidence.',
            'compare': 'Compare executed alternatives using common criteria; resolve tradeoffs or retain an uncertain incumbent.'}
        return tuple(OptimizationField('parameters.instructions.' + key, 'string', descriptions[key], value,
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
        if not isinstance(value, dict) or set(value) != {'instructions'} or set(value['instructions']) != set(EvaluatorInstructions.__dataclass_fields__):
            raise ValueError('evaluator requires exactly its instruction fields')
        return EvaluatorInstructions(**value['instructions'])

    def validate(self, text):
        self.parse(text)

    def validate_options(self, options):
        allowed = {'parameters.instructions.' + key for key in EvaluatorInstructions.__dataclass_fields__}
        if not isinstance(options, dict) or set(options) - {'editable_fields', 'bounds'} or options.get('bounds'):
            raise ValueError('evaluator grants accept prompt fields without numeric bounds')
        fields = options.get('editable_fields', sorted(allowed))
        if not isinstance(fields, list) or not fields or len(set(fields)) != len(fields) or set(fields) - allowed:
            raise ValueError('invalid evaluator prompt grant')

    def validate_change(self, text, options):
        value = self.parse(text)
        allowed = set(options.get('editable_fields', ('parameters.instructions.' + key for key in asdict(self.instructions))))
        for key, before in asdict(self.instructions).items():
            if 'parameters.instructions.' + key not in allowed and getattr(value, key) != before:
                raise ValueError('candidate changed a fixed evaluator prompt')

    def prepare_trial(self, config, text):
        raise ValueError('evaluator changes require an independently measured fixed-I comparison')
