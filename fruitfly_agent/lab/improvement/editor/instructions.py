"""Declarative I instructions, independent of any execution component."""
from fruitfly_agent.runtime_spec.documents import parameter_default
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec, OptimizationField
from dataclasses import asdict, dataclass, field
import json
from .configuration import EditorSettings

from fruitfly_agent.improvement.contracts.optimization import TargetBinding, TargetSnapshot
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.improvement.contracts.validation import bounded


@dataclass(frozen=True)
class EditorInstructions:
    system: str = (field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'instructions.system')))
    reflect: str = (field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'instructions.reflect')))
    propose: str = (field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'instructions.propose')))

    component_context: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'instructions.component_context'))
    navigation: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'instructions.navigation'))
    submission: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'instructions.submission'))
    direction: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'instructions.direction'))
    recover_evidence: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'instructions.recover_evidence'))
    no_evidence: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'instructions.no_evidence'))
    repair: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'instructions.repair'))
    write_file: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'instructions.write_file'))
    delete_file: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'instructions.delete_file'))
    list_targets: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'instructions.list_targets'))
    describe_target: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'instructions.describe_target'))
    submit_candidate: str = field(default_factory=lambda: parameter_default(__package__ + '.methods.workspace', 'defaults.yaml', 'instructions.submit_candidate'))

    def __post_init__(self):
        for value in asdict(self).values():
            bounded(value, 16000)

    def serialize(self):
        return canonical_json(asdict(self))

    @classmethod
    def parse(cls, text):
        def unique(pairs):
            result = {}
            for name, value in pairs:
                if name in result:
                    raise ValueError('duplicate editor instruction field')
                result[name] = value
            return result
        value = json.loads(text, object_pairs_hook=unique)
        fields = set(cls.__dataclass_fields__)
        if not isinstance(value, dict) or set(value) != fields:
            raise ValueError('editor instructions require exactly the registered stage fields')
        return cls(**value)


class EditorInstructionTarget:
    optimization = OptimizationSpec('I', 'parameters', required_capabilities=frozenset({'improver-comparison'}), default_selected=False)
    structured_parameters = True
    label = 'Improvement editor instructions'
    component_kind = 'improvement-instructions'
    required_capabilities = frozenset({'improver-comparison'})
    adoption_roles = frozenset({'I'})

    def __init__(self, instructions=None, *, text=None, settings=None):
        self.instructions = instructions or EditorInstructions()
        self.settings = EditorSettings.from_dict(settings)
        self.text = canonical_json({'instructions':asdict(self.instructions), 'settings':asdict(self.settings)}) if text is None else text
        if self.parse_document(self.text) != self.instructions or EditorSettings.from_dict(json.loads(self.text)['settings']) != self.settings:
            raise ValueError('editor source differs from installed instructions')

    def snapshot(self):
        return TargetSnapshot('improvement-editor', self.text, TargetBinding('artifact','improvement-editor'), 'editor-instructions', 'I')

    def describe_fields(self, text=None):
        instructions = self.instructions if text is None else self.parse_document(text)
        descriptions = {
            'system':'Overall editor analysis, evidence use and candidate procedure.',
            'propose':'Form a testable behavioral hypothesis from observed evidence.',
            'reflect':'Derive reusable lessons with limitations from executed contrasts.'}
        return tuple(OptimizationField('parameters.instructions.'+name,'string',descriptions.get(name, 'Configure ' + name.replace('_', ' ') + ' guidance.'),value,
            getattr(EditorInstructions(),name),unit='characters',minimum=1,maximum=16000) for name,value in asdict(instructions).items())

    @staticmethod
    def parse_document(text):
        def unique(pairs):
            result={}
            for key,value in pairs:
                if key in result:raise ValueError('duplicate editor field')
                result[key]=value
            return result
        value=json.loads(text,object_pairs_hook=unique)
        if not isinstance(value,dict) or set(value)!={'instructions', 'settings'} or not isinstance(value['instructions'],dict) or set(value['instructions'])!=set(EditorInstructions.__dataclass_fields__):
            raise ValueError('editor candidate requires exactly its instructions')
        EditorSettings.from_dict(value['settings'])
        return EditorInstructions(**value['instructions'])

    def validate(self,text):
        self.parse_document(text)
        if EditorSettings.from_dict(json.loads(text)['settings']) != self.settings:
            raise ValueError('candidate changed protected role settings')

    def prepare_trial(self,config,text):
        raise ValueError('editor changes require an independent improver comparison')

    def validate_options(self,options):
        allowed={'parameters.instructions.'+name for name in EditorInstructions.__dataclass_fields__}
        fields=options.get('editable_fields',list(allowed))
        if not isinstance(options,dict) or set(options)-{'editable_fields','bounds'} or options.get('bounds') or not isinstance(fields,list) or not fields or len(set(fields))!=len(fields) or set(fields)-allowed:
            raise ValueError('editor grants permit instruction fields only')

    def validate_change(self,text,options):
        self.validate(text)
        value=self.parse_document(text)
        allowed=options.get('editable_fields',['parameters.instructions.'+name for name in EditorInstructions.__dataclass_fields__])
        for name in EditorInstructions.__dataclass_fields__:
            if 'parameters.instructions.'+name not in allowed and getattr(value,name)!=getattr(self.instructions,name):
                raise ValueError('candidate changed a fixed editor instruction')
