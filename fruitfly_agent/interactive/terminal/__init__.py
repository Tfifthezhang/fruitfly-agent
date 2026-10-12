"""Built-in stdlib terminal adapter for the interactive application."""

from fruitfly_agent.interactive.terminal.bindings import TerminalBindings, TerminalSession, ImprovementClients
from fruitfly_agent.interactive.terminal.commands import TerminalCommandHandler, TerminalCommandRegistry
from fruitfly_agent.interactive.terminal.features.configuration.menu import TerminalConfigurationFrontend
from fruitfly_agent.interactive.terminal.features.evaluation.menu import TerminalEvaluationFrontend
from fruitfly_agent.interactive.terminal.frontend import TerminalFrontend
from fruitfly_agent.interactive.terminal.io.input import (
    LineEditor,
    ReadlineLineEditor,
    StreamLineEditor,
    create_line_editor,
)
from fruitfly_agent.interactive.terminal.rendering.renderer import TerminalRenderer
from fruitfly_agent.interactive.terminal.features.resume.menu import TerminalResumeFrontend
from fruitfly_agent.interactive.terminal.io.screen import transient_screen

__all__ = [
    "TerminalConfigurationFrontend",
    "TerminalEvaluationFrontend",
    "LineEditor",
    "ReadlineLineEditor",
    "StreamLineEditor",
    "TerminalFrontend",
    "TerminalBindings",
    "ImprovementClients",
    "TerminalSession",
    "TerminalCommandHandler",
    "TerminalCommandRegistry",
    "TerminalRenderer",
    "TerminalResumeFrontend",
    "create_line_editor",
    "transient_screen",
]
