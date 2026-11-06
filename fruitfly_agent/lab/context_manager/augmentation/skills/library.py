"""One effective library for packaged, workspace and candidate Skill text."""
from importlib.resources import files
from pathlib import Path
import yaml

from fruitfly_agent.improvement.contracts.versions import SnapshotFile, StateSnapshot, canonical_json
from fruitfly_agent.lab.catalog.adapters.collections import DocumentsTarget, collection_surface, parse_documents
from fruitfly_agent.improvement.contracts.text import TEXT_TARGET_PREFIX
from fruitfly_agent.improvement.contracts.versions import STATE_SNAPSHOTS_COMPONENT
from fruitfly_agent.lab.context_manager.augmentation.skills.methods.indexed_documents.parser import Skill, load_skills
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


def state_surface():
    def normalize(parameters):
        if (not isinstance(parameters, dict) or set(parameters) != {'content'}
                or not isinstance(parameters['content'], dict) or set(parameters['content']) != {'documents'}
                or not isinstance(parameters['content']['documents'], str)):
            raise ValueError('Skill state requires content.documents')
        text = parameters['content']['documents']
        if text:
            text = canonical_json(validate_skills(parse_documents(text)))
        return {'content': {'documents': text}}
    return collection_surface('skill-library', normalize=normalize,
        default_resource=(__package__, 'skill-library.yaml'), factory=create_target)


def create_target(state, context, parameters):
    values = parameters['content']
    if values['documents']:
        entries = validate_skills(parse_documents(values['documents']))
    else:
        entries = builtin_entries()
        from fruitfly_agent.lab.catalog.assembly import require_workspace_path
        root = require_workspace_path(context.workspace, context.model_parameters['root'], name='Skill root')
        captured = capture_skills(root, context.workspace)
        for skill in captured.skills:
            directory = Path(skill.file_path).parent.relative_to(context.workspace).as_posix()
            references = {f.path[len(directory) + 1:]: f.content for f in captured.snapshot.files
                if f.path.startswith(directory + '/') and f.path != Path(skill.file_path).relative_to(context.workspace).as_posix()}
            entries.append(package_entry(skill, references, str(Path(skill.file_path).relative_to(context.workspace)),
                'workspace', 'User supplied; review source terms'))
        entries = validate_skills(entries)
    return DocumentsTarget(state_surface(), {'documents': canonical_json(entries)}, label='Installed Skills', kind='skill',
        validate_documents=validate_skills, mutable={'description', 'body', 'references'},
        visible=lambda entry: not entry['disabled'],
        freeze_documents=lambda documents: capture_library(documents, context.workspace).freeze())
