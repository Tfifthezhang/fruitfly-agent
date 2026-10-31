"""Load the installed-agent bridge against a local Harbor protocol double."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import json

from fruitfly_eval.harbor.host import HostConfig, Mount


def prepared_harbor(root, names=("task",)):
    """Minimal explicit prepared input for adapter command/secret tests."""
    host = HostConfig(root / "host.yaml", root / "cache", "/opt/runtime/bin/python",
                      (Mount(root / "runtime", "/opt/runtime"),))
    receipt = {"runtime": {"python": host.python, "environment": host.runtime_env(),
                            "host": host.identity(), "mounts": [m.to_dict() for m in host.mounts],
                            "source": str(root / "source"), "installation": {"version": "0.1"}},
               "tasks": [{"id": name, "name": name.rsplit("/", 1)[-1],
                          "path": str(root / "tasks" / name.rsplit("/", 1)[-1])} for name in names]}
    return host, receipt


def installed_agent_inputs(agent, root):
    """Stage the files that the bridge receives after job preparation."""
    host, receipt = prepared_harbor(root)
    agent.config_path = root / "config.yaml"
    agent.model_catalog_path = root / "models.yaml"
    agent.config_path.write_text("offline configuration")
    agent.model_catalog_path.write_text("offline catalog")
    (root / "preparation.json").write_text(json.dumps(receipt))
    agent.runtime_python = host.python
    agent.runtime_environment = host.runtime_env()
    agent.preparation = receipt
    return receipt


class InstalledAgentDouble:
    def _redact_command(self, command):
        return command  # Fixtures contain no credentials.

    async def _exec(self, environment, command, **kwargs):
        return await environment.exec(command=command, **kwargs)


def load_harbor_agent():
    """Keep bridge tests independent of the optional SDK and its constructors."""
    attributes = {
        "harbor.agents.capabilities": {"AgentCapabilities": SimpleNamespace},
        "harbor.agents.installed.base": {
            "BaseInstalledAgent": InstalledAgentDouble,
            "with_prompt_template": lambda function: function,
        },
        "harbor.environments.base": {"BaseEnvironment": object},
        "harbor.models.agent.context": {"AgentContext": object},
    }
    modules = {}
    for name, values in attributes.items():
        module = ModuleType(name)
        module.__dict__.update(values)
        modules[name] = module
    path = Path(__file__).resolve().parents[2] / "fruitfly_eval" / "harbor_agent.py"
    spec = importlib.util.spec_from_file_location("_fruitfly_harbor_bridge_test", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module.FruitFlyHarborAgent


def load_harbor_environment():
    """Exercise the extension constructor without importing optional SDK code."""
    class DockerEnvironmentDouble:
        def __init__(self, *args, **kwargs):
            self.constructor = kwargs

    modules = {}
    for name, attributes in {
        "harbor.environments.docker.docker": {"DockerEnvironment": DockerEnvironmentDouble},
        "harbor.models.trial.config": {"ServiceVolumeConfig": dict},
    }.items():
        module = ModuleType(name)
        module.__dict__.update(attributes)
        modules[name] = module
    path = Path(__file__).resolve().parents[2] / "fruitfly_eval/harbor/docker_environment.py"
    spec = importlib.util.spec_from_file_location("fruitfly_eval.harbor._environment_test", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module.PreparedDockerEnvironment
