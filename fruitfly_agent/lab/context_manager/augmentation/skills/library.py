"""One effective library for packaged, workspace and candidate Skill text."""
from importlib.resources import files
from pathlib import Path
import yaml

from fruitfly_agent.improvement.contracts.versions import SnapshotFile, StateSnapshot, canonical_json
from fruitfly_agent.lab.catalog.models import MechanismDefinition
from fruitfly_agent.lab.catalog.components import ComponentSpec
from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution, ParameterDescriptor
from fruitfly_agent.lab.improvement.targets.documents import DocumentsTarget, parse_documents
from fruitfly_agent.lab.improvement.targets.text import TEXT_TARGET_PREFIX
from fruitfly_agent.improvement.contracts.versions import STATE_SNAPSHOTS_COMPONENT
from .catalog import Skill, load_skills
from .resources import SkillResources, capture_skills
from .packages import package_entry, validate_skills


def builtin_entries():
    root = files(__package__).joinpath('builtin')
    manifest = yaml.safe_load(root.joinpath('manifest.yaml').read_text(encoding='utf-8'))
    result = []
    for name in manifest['skills']:
        raw = root.joinpath(name, 'SKILL.md').read_text(encoding='utf-8')
        header, body = raw.split('---', 2)[1:]
        meta = yaml.safe_load(header)
        # Repository navigation is not a portable runtime reference.
        body = body.replace('[Up: Built-in coding Skills](../README.md)\n\n', '')
        skill = Skill(meta['name'], meta['description'], body.strip(), name, source_text=raw)
        result.append(package_entry(skill, {}, 'FruitFlyAgent builtin', '0.1', 'MIT'))
    return validate_skills(result)


def capture_library(entries, workspace):
    entries = validate_skills(entries)
    skills, documents = [], []
    for entry in sorted(entries, key=lambda e: e['id']):
        directory = '.fruitfly/skill-library/' + entry['id']
        path = directory + '/SKILL.md'
        raw = '---\n' + yaml.safe_dump({'name': entry['name'], 'description': entry['description'],
            'disable-model-invocation': entry['disabled']}, sort_keys=False) + '---\n\n' + entry['body']
        skills.append(Skill(entry['name'], entry['description'], entry['body'], str(workspace / path), entry['disabled'], raw))
        documents.append(SnapshotFile(path, raw))
        documents.extend(SnapshotFile(directory + '/' + p, text) for p, text in sorted(entry['references'].items()))
    return SkillResources(workspace, tuple(skills), StateSnapshot(tuple(documents), roots=('.fruitfly/skill-library',)), ())


def definition():
    return MechanismDefinition(MechanismDescriptor('skill-library', 'Retained Skill library',
        'Load portable coding procedures and expose their descriptions, bodies and references as S.',
        contributions=(MechanismContribution('capability', 'context'),), install_order=29, default_enabled=True,

        parameters=(ParameterDescriptor('documents', 'string', 'Skill documents',
            'JSON Skill entries; empty text seeds packaged and workspace Skills.', ''),)), install,
        prepare_targets=prepare_standalone,
        configuration_role='S', default_resource=(__package__, 'skill-library.yaml'),
        parameter_paths={'documents': 'content.documents'},
        configuration_edit=lambda fields, bounds: _edit(fields, bounds),
        validate_parameters=lambda values: validate_skills(parse_documents(values.get('documents', ''))) if values.get('documents') else None,
        component_specs=lambda values, enabled: (ComponentSpec('skill-library', 'S', 'mechanism-parameters',
            'mechanism-parameters-v1', frozenset({'configuration-materialization'})),) if enabled else (),
        implementation_path='fruitfly_agent/lab/context_manager/augmentation/skills/library.py',
        documentation_path='fruitfly_agent/lab/context_manager/augmentation/skills/README.md')


def _edit(fields, bounds):
    if fields != ['parameters.content.documents'] or bounds:
        raise ValueError('Skill library grants require content.documents without numeric bounds')
    return {'editable_fields': fields, 'bounds': {}}


def install(state, context, values):
    return state.with_component('skill-library-preparation', values)


def prepare_library(state, context, values, root):
    if values['documents']:
        entries = validate_skills(parse_documents(values['documents']))
    else:
        entries = builtin_entries()
        # The workspace root is owned by the existing catalog configuration.
        captured = capture_skills(root, context.workspace)
        for skill in captured.skills:
            directory = Path(skill.file_path).parent.relative_to(context.workspace).as_posix()
            references = {f.path[len(directory) + 1:]: f.content for f in captured.snapshot.files
                if f.path.startswith(directory + '/') and f.path != Path(skill.file_path).relative_to(context.workspace).as_posix()}
            entries.append(package_entry(skill, references, str(Path(skill.file_path).relative_to(context.workspace)),
                'workspace', 'User supplied; review source terms'))
        entries = validate_skills(entries)
    values = {'documents': canonical_json(entries)}
    target = DocumentsTarget(definition(), values, validate_documents=validate_skills,
        mutable={'description', 'body', 'references'},
        freeze_documents=lambda documents: capture_library(documents, context.workspace).freeze())
    captured = capture_library(entries, context.workspace)
    return (state.with_component(TEXT_TARGET_PREFIX + 'skill-library', target)
        .with_component('skill-library-resources', captured)
        .with_component(STATE_SNAPSHOTS_COMPONENT, (*state.components.get(STATE_SNAPSHOTS_COMPONENT, ()), target)))


def prepare_standalone(state, context):
    if 'skill-library-preparation' in state.components and TEXT_TARGET_PREFIX + 'skill-library' not in state.components:
        return prepare_library(state, context, state.components['skill-library-preparation'], context.workspace / '.skills')
    return state
