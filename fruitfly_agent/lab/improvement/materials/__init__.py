"""Freeze complete task inputs independently of benchmark or scoring contracts."""
from __future__ import annotations

from pathlib import Path
from mimetypes import guess_type

from ..contracts.pipeline import Resource, TaskMaterial, relative_path


class WorkspaceTaskSource:
    def __init__(self, root, artifacts):
        self.root, self.artifacts = Path(root).resolve(), artifacts

    def freeze(self, task_id, instruction, *, paths=(), environment_id='isolated-local'):
        from fruitfly_agent.lab.environment.permissions import PermissionAuthorizer, PermissionPolicy
        authorizer = PermissionAuthorizer(PermissionPolicy(self.root))
        resources = []
        for name in paths:
            relative_path(name)
            path = self.root / name
            authorizer.check(name, 'read')
            if not path.resolve().is_relative_to(self.root) or any(p.is_symlink() for p in (path, *path.parents)):
                raise ValueError('task input escapes its declared material root')
            if not path.is_file():
                raise ValueError('task inputs must name existing files')
            resources.append(Resource(name, self.artifacts.put(path.read_bytes()),
                                      guess_type(name)[0] or 'application/octet-stream'))
        return TaskMaterial(task_id, instruction, tuple(resources), environment_id, 'workspace')


__all__ = ['WorkspaceTaskSource']
