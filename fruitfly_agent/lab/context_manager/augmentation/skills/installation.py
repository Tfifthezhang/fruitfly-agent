"""Offline admission for prepared Skill packages; no downloads or activation."""
from .packages import SkillPackage, SkillPackageSource, validate_skills


def prepare_installation(existing, source: SkillPackageSource):
    package = source.load()
    if not isinstance(package, SkillPackage):
        raise TypeError('Skill source must return SkillPackage')
    if not package.source or not package.revision:
        raise ValueError('Skill package requires source and revision')
    if package.dependencies:
        raise ValueError('Skill package dependencies need an external adapter; text-only installation supports none')
    current = validate_skills(list(existing))
    added = validate_skills(list(package.entries))
    if {e['id'] for e in current} & {e['id'] for e in added}:
        raise ValueError('Skill installation identity conflict')
    return tuple(validate_skills(sorted([*current, *added], key=lambda e: e['id'])))
