"""Load the installed-agent bridge against a local Harbor protocol double."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import patch


class InstalledAgentDouble:
    def _redact_command(self, command):
        return command  # Fixtures contain no credentials.

    async def _exec(self, environment, command, **kwargs):
        return await environment.exec(command=command, **kwargs)


def load_harbor_agent():
    """Keep bridge tests independent of the optional SDK and its constructors."""
    attributes = {
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
    path = Path(__file__).resolve().parents[2] / "eval" / "harbor_agent.py"
    spec = importlib.util.spec_from_file_location("_fruitfly_harbor_bridge_test", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module.FruitFlyHarborAgent
