"""Pure model alias and executor-inheritance grammar shared by all hosts."""
from __future__ import annotations

from typing import Mapping, TypeAlias

ModelRoleBinding: TypeAlias = str | Mapping[str, str]


def normalize_model_roles(roles: Mapping[str, ModelRoleBinding]) -> dict[str, ModelRoleBinding]:
    if not isinstance(roles, Mapping):
        raise ValueError('model roles must be a mapping')
    result: dict[str, ModelRoleBinding] = {}
    for role, binding in roles.items():
        if not isinstance(role, str) or not role:
            raise ValueError('model role names must be nonempty strings')
        if isinstance(binding, str) and binding.strip() and binding == binding.strip():
            result[role] = binding
        elif role != 'executor' and isinstance(binding, Mapping) and dict(binding) == {'inherit': 'executor'}:
            result[role] = {'inherit': 'executor'}
        else:
            raise ValueError('model roles require catalog aliases or {inherit: executor}; executor requires an alias')
    return result


def resolve_model_roles(roles: Mapping[str, ModelRoleBinding], executor: str) -> dict[str, str]:
    if not isinstance(executor, str) or not executor.strip():
        raise ValueError('select an executor model alias before resolving roles')
    return {**{role: binding if isinstance(binding, str) else executor
        for role, binding in normalize_model_roles(roles).items()}, 'executor': executor}
