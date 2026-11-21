"""Declared connection behavior, independent of frontend and application state."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from ..auth.contracts import AuthMethod

@dataclass(frozen=True)
class ConnectionProfile:
    integration: str
    account: str = ''
    credential_env: str = ''

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ConnectionProfile:
        import re

        if not isinstance(value, dict):
            raise ValueError('Connection requires a mapping')
        integration = value.get('integration')
        if not isinstance(integration, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', integration):
            raise ValueError('Connection integration must be an identifier')
        if value.keys() == {'integration', 'account'}:
            account = value['account']
            if isinstance(account, str) and account and all(ord(c) >= 33 for c in account):
                return cls(integration, account=account)
        if value.keys() == {'integration', 'credential'}:
            credential = value['credential']
            if isinstance(credential, dict) and credential.keys() == {'env'}:
                name = credential['env']
                if isinstance(name, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
                    return cls(integration, credential_env=name)
        raise ValueError('Connection requires one account or a credential.env variable name')

    def to_dict(self) -> dict[str, Any]:
        if self.credential_env:
            return {'integration': self.integration, 'credential': {'env': self.credential_env}}
        return {'integration': self.integration, 'account': self.account}

@dataclass(frozen=True)
class ConnectionDefinition:
    id: str
    label: str
    service: str
    protocol: str
    sdk: str
    endpoint: str
    method: AuthMethod
    parse_models: Callable[[Any], list[dict[str, Any]]]
    refresh: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    request_policy: Any = None
    output_enforced: bool = True
    models_path: str = '/models'
    begin_login: Any = None
    authorization_url: Any = None
    complete_login: Any = None
    revoke: Any = None
