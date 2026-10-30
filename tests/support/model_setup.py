"""Temporary model configuration and scripted frontend fixtures."""
import io
from pathlib import Path
from fruitfly_agent.interactive import TerminalConfigurationFrontend
from fruitfly_agent.run import RunApplicationFactory
from tests.support.terminal import ScriptedLines

class ModelSetupWorkspace:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.factory = RunApplicationFactory(cwd=self.root, environment={}, allow_incomplete=True)
        self.controller = self.factory.configuration
        self.setup = self.controller.model_setup
        (self.root / ".fruitfly").mkdir(exist_ok=True)
        self.values = dict(profile="local", model="offline-model", base_url="",
                           context_window="8192", max_output_tokens="1024", api_key_env="")

    def stage(self, **changes):
        return self.setup.stage("openai", {**self.values, **changes}, "offline-placeholder")

    def frontend(self, *lines, secret="offline-placeholder"):
        self.output = io.StringIO()
        return TerminalConfigurationFrontend(self.controller, input_stream=io.StringIO(secret + "\n"),
            output_stream=self.output, line_editor=ScriptedLines(*lines))
