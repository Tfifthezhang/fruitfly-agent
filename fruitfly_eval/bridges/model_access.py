"""Bind model access transport to a job without benchmark or model-name dispatch."""
from pathlib import Path
import platform
from typing import Any
from fruitfly_eval.harbor.model_access import TARGET


def trial_relay_directory(directory: Path, trial: Path) -> Path:
    """Derive the same private communication mount in engine and Agent hosts."""
    from hashlib import sha256
    return directory / sha256(str(trial.resolve()).encode()).hexdigest()[:20]


def configure_model_network(agent: dict[str, Any], models: Path) -> None:
    """Allow only declared direct inference hosts through engine phase allowlists."""
    from urllib.parse import urlsplit
    from fruitfly_agent.providers.registry import load_model_specs
    hosts = list(agent.get('extra_allowed_hosts', []))
    for spec in load_model_specs(models).values():
        if not spec.access and spec.provider.base_url:
            hostname = urlsplit(spec.provider.base_url).hostname
            if hostname:
                hosts.append(hostname)
    if hosts:
        agent['extra_allowed_hosts'] = list(dict.fromkeys(hosts))


def configure_model_access(environment: dict[str, Any], agent: dict[str, Any], *,
                           required: bool, directory: Path | None, settings: dict[str, Any]) -> None:
    if not required:
        return
    if directory is None:
        raise ValueError('Subscription execution requires an owned relay directory')
    agent.setdefault('kwargs', {}).update(model_relay_directory=str(directory), model_relay_settings=dict(settings))
    if not settings:
        if platform.system() != 'Linux':
            raise ValueError('Subscription models on Docker Desktop require model_relay TLS settings')
        environment.setdefault('mounts', []).append({'type': 'bind', 'source': str(directory),
                                                   'target': TARGET, 'read_only': False})
    else:
        from urllib.parse import urlsplit
        hostname = urlsplit(settings['network_url']).hostname
        if hostname:
            agent['extra_allowed_hosts'] = list(dict.fromkeys([*agent.get('extra_allowed_hosts', []), hostname]))
