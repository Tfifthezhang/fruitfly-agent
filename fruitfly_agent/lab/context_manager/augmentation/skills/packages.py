"""Portable text Skill packages; external sources implement this public seam."""
from dataclasses import dataclass
from typing import Protocol
import re
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash


@dataclass(frozen=True)
class SkillPackage:
    entries: tuple[dict, ...]
    source: str
    revision: str
    dependencies: tuple[str, ...] = ()


class SkillPackageSource(Protocol):
    def load(self) -> SkillPackage: ...


def validate_skills(entries):
    if not isinstance(entries, list) or len(entries) > 128:
        raise ValueError('Skill library requires at most 128 entries')
    identities = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'id', 'name', 'description', 'body', 'references', 'origin', 'disabled'}:
            raise ValueError('invalid Skill fields')
        if (not isinstance(entry['id'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', entry['id'])
                or entry['id'] in identities or entry['name'] != entry['id'] or type(entry['disabled']) is not bool):
            raise ValueError('invalid or duplicate Skill identity')
        identities.add(entry['id'])
        for key, limit in (('description', 2000), ('body', 30000)):
            if not isinstance(entry[key], str) or not entry[key].strip() or len(entry[key]) > limit:
                raise ValueError('invalid Skill ' + key)
        if not isinstance(entry['references'], dict) or len(entry['references']) > 32:
            raise ValueError('invalid Skill references')
        from pathlib import PurePosixPath
        for name, text in entry['references'].items():
            if not isinstance(name, str):
                raise ValueError('unsupported Skill reference')
            path = PurePosixPath(name)
            if (not isinstance(name, str) or path.is_absolute() or '..' in path.parts
                    or str(path) != name or '%' in name or '\\' in name or name == 'SKILL.md'
                    or path.suffix not in {'.md', '.txt'} or not isinstance(text, str) or len(text) > 128000):
                raise ValueError('unsupported Skill reference')
        origin = entry['origin']
        if (not isinstance(origin, dict) or set(origin) != {'source', 'revision', 'digest', 'license'}
                or any(not isinstance(v, str) or not v for v in origin.values())
                or not re.fullmatch(r'sha256:[a-f0-9]{64}', origin['digest'])):
            raise ValueError('invalid Skill provenance')
    # Keep original values isolated from a caller that edits its package after admission.
    import json
    result = json.loads(canonical_json(entries))
    if len(canonical_json(result).encode()) > 2_000_000:
        raise ValueError('Skill package exceeds its byte budget')
    return result


def package_entry(skill, references, source, revision, license):
    if skill.source_text.startswith('---'):
        import yaml
        parts = skill.source_text.split('---', 2)
        meta = yaml.safe_load(parts[1]) if len(parts) == 3 else None
        if (not isinstance(meta, dict) or set(meta) - {'name', 'description', 'disable-model-invocation'}
                or ('disable-model-invocation' in meta and type(meta['disable-model-invocation']) is not bool)):
            raise ValueError('unsupported Skill metadata or dependency declaration')
    return {'id': skill.name, 'name': skill.name, 'description': skill.description,
        'body': skill.content.strip(), 'references': references, 'disabled': skill.disable_model_invocation,
        'origin': {'source': source, 'revision': revision,
            'digest': content_hash(canonical_json({'text': skill.source_text, 'references': references})), 'license': license}}
