"""One bounded Skill metadata/body snapshot for local and SSH runtimes."""
from dataclasses import dataclass
from pathlib import Path
import os

from fruitfly_agent.improvement.contracts.versions import SnapshotFile, StateSnapshot
from fruitfly_agent.lab.context_manager.augmentation.skills.methods.indexed_documents.parser import load_skills, Skill


@dataclass(frozen=True)
class SkillResources:
    workspace: Path
    skills: tuple[Skill, ...]
    snapshot: StateSnapshot
    diagnostics: tuple[str, ...]

    def freeze(self):
        return self.snapshot

    def mount(self, resources, name='skills'):
        documents = {entry.path: entry.content.encode('utf-8') for entry in self.snapshot.files}
        prefix = resources.mount(name, lambda path: documents[path])
        locations = {skill.file_path: prefix + Path(skill.file_path).relative_to(self.workspace).as_posix()
                     for skill in self.skills}
        from .methods.indexed_documents.parser import render_skills_xml
        documents['INDEX.md'] = render_skills_xml(list(self.skills), locations=locations).encode('utf-8')
        return {**locations, '__catalog__': prefix + 'INDEX.md'}


def capture_skills(root, workspace):
    root, workspace = Path(root), Path(workspace).resolve()
    relative_root = root.relative_to(workspace).as_posix()
    result = load_skills(root)
    diagnostics = list(result.diagnostics)
    documents = {Path(skill.file_path).relative_to(workspace).as_posix(): skill.source_text
                 for skill in result.skills}
    total = sum(len(text.encode('utf-8')) for text in documents.values())
    if len(documents) > 512 or total > 8 * 1024 * 1024:
        raise ValueError('Skill resource snapshot exceeds its bounds')
    if any('%' in name or '\\' in name for name in documents):
        raise ValueError('Skill source has an unsupported resource path')
    pending, visited = [(root, 0)], 0
    while pending:
        directory, depth = pending.pop()
        if not directory.is_dir():
            continue
        try:
            with os.scandir(directory) as entries:
                children = []
                for entry in entries:
                    visited += 1
                    if visited > 4096:
                        raise ValueError('Skill resource entry limit exceeded')
                    children.append(Path(entry.path))
        except OSError as exc:
            diagnostics.append('Skill resource listing failed: ' + str(exc))
            continue
        for path in sorted(children):
            if path.name.startswith('.') or path.is_symlink():
                continue
            if path.is_dir():
                if depth >= 32:
                    diagnostics.append('Skill resource depth limit: ' + str(path))
                else:
                    pending.append((path, depth + 1))
                continue
            if path.suffix.lower() not in {'.md', '.txt'}:
                continue
            relative = path.relative_to(workspace).as_posix()
            if '%' in relative or '\\' in relative:
                diagnostics.append('Unsupported Skill resource path: ' + relative)
                continue
            try:
                with path.open('rb') as stream:
                    data = stream.read(1_000_001)
                if len(data) > 1_000_000:
                    diagnostics.append('Skill resource byte limit: ' + relative)
                    continue
                text = data.decode('utf-8')
            except (OSError, UnicodeError) as exc:
                diagnostics.append('Skill resource read failed: ' + str(exc))
                continue
            if relative in documents:
                if documents[relative] != text:
                    raise ValueError('Skill changed during assembly; reload: ' + relative)
                continue
            total += len(data)
            if total > 8 * 1024 * 1024 or len(documents) >= 512:
                raise ValueError('Skill resource snapshot exceeds its bounds')
            documents[relative] = text
    snapshot = StateSnapshot(tuple(SnapshotFile(path, text) for path, text in documents.items()), roots=(relative_root,))
    return SkillResources(workspace, tuple(result.skills), snapshot, tuple(diagnostics))
