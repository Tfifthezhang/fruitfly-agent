"""Pure, responsive startup rendering for the line-oriented terminal UI."""

from __future__ import annotations

from fruitfly_agent.interactive.contracts.models import InteractiveStatus
from fruitfly_agent.interactive.terminal.rendering.branding import FRUIT_FLY_MARK, FRUIT_FLY_SMALL_MARK, FRUIT_FLY_TINY_MARK, WORDMARK_FONT
from fruitfly_agent.interactive.terminal.io.text import cell_width, pad_cells, truncate_cells, wrap_cells, safe_terminal_text


_BLUE = "\x1b[34m"
_BOLD = "\x1b[1m"
_CYAN = "\x1b[36m"
_DIM = "\x1b[2m"
_RESET = "\x1b[0m"

_GLYPH_COLORS = {"█": _BLUE}
_ART_WIDTH = max(cell_width(line) for line in FRUIT_FLY_MARK)
_WORDMARK_WIDTH = max(
    cell_width(" ".join(WORDMARK_FONT[letter][row] for letter in "FRUITFLY"))
    for row in range(len(WORDMARK_FONT["F"]))
)
_BRAND_COPY_WIDTH = max(
    _WORDMARK_WIDTH,
    cell_width("The model organism for agent research."),
)
_SIDE_BY_SIDE_MIN_WIDTH = _ART_WIDTH + 3 + _BRAND_COPY_WIDTH


def render_welcome(
    status: InteractiveStatus,
    *,
    columns: int,
    terminal_ui: bool,
    color: bool,
) -> str:
    """Render one startup block; never emits ANSI outside a capable TTY."""
    width = max(4, columns - 1)
    if not terminal_ui:
        lines = [f"FruitFlyAgent interactive · {status.model}",
                 *_environment_lines(status), "Type a task, or /config for settings and /help for commands."]
        return "\n".join(lines) + "\n"

    if width >= _SIDE_BY_SIDE_MIN_WIDTH:
        lines = _wide_lines(status, width)
    elif width >= _ART_WIDTH + 3 + cell_width("FruitFlyAgent"):
        lines = _medium_lines(status, width)
    else:
        lines = _compact_lines(status, width)
    if color:
        lines = _colorize(lines)
    return "\n".join(lines) + "\n"


def _wide_lines(
    status: InteractiveStatus,
    width: int,
) -> list[str]:
    wordmark = _render_word("FRUITFLY")
    right = [
        "",
        "",
        *wordmark,
        _brand_line(),
        "The model organism for agent research.",
    ]
    right.extend("" for _ in range(len(FRUIT_FLY_MARK) - len(right)))
    header = [
        truncate_cells(
            f"{pad_cells(FRUIT_FLY_MARK[index], _ART_WIDTH)}   {right[index]}",
            width,
        )
        for index in range(len(FRUIT_FLY_MARK))
    ]
    return ["", *header, "", *_status_lines(status, width), "", _tip_line(width), ""]


def _medium_lines(
    status: InteractiveStatus,
    width: int,
) -> list[str]:
    right = ['', '', 'FruitFlyAgent', 'AGENT', '', 'The model organism for agent research.']
    header = [truncate_cells(f'{pad_cells(line, _ART_WIDTH)}   {right[i] if i < len(right) else ""}', width)
              for i, line in enumerate(FRUIT_FLY_MARK)]
    return ['', *header, '', *_status_lines(status, width), '', _tip_line(width), '']


def _compact_lines(
    status: InteractiveStatus,
    width: int,
) -> list[str]:
    brand = "✦ FruitFlyAgent"
    mark = FRUIT_FLY_SMALL_MARK
    if max(map(cell_width, mark)) > width:
        mark = FRUIT_FLY_TINY_MARK
    session = "resumed" if status.message_count else "new session"
    lines = [
        "",
        *(truncate_cells(line, width) for line in mark),
        truncate_cells(brand, width),
        truncate_cells("The model organism for agent research.", width),
        truncate_cells(f"{status.model} · {session}", width),
    ]
    if status.prompt_label:
        lines.append(truncate_cells(f"prompt: {status.prompt_label}", width))
    lines.extend([
        *_environment_lines(status, width),
        *wrap_cells("/config settings · /resume history · /help commands", width),
        "",
    ])
    return lines


def _render_word(word: str) -> list[str]:
    return [
        " ".join(WORDMARK_FONT[letter][row] for letter in word)
        for row in range(len(WORDMARK_FONT[word[0]]))
    ]


def _brand_line() -> str:
    return "AGENT"


def _status_lines(status: InteractiveStatus, width: int) -> list[str]:
    session = (
        f"resumed · {status.message_count} messages"
        if status.message_count
        else "new · 0 messages"
    )
    lines = [
        _labeled_line("model", status.model, width),
    ]
    if status.prompt_label:
        lines.append(_labeled_line("prompt", status.prompt_label, width))
    lines.extend([
        *_environment_lines(status, width),
        _labeled_line("session", session, width),
    ])
    return lines


def _environment_lines(status: InteractiveStatus, width: int | None = None) -> list[str]:
    environment = status.execution_environment
    rows = [("workspace", status.working_directory),
            ("execution", environment.label if environment is not None else "Unavailable")]
    if environment is not None:
        if environment.server:
            rows.append(("server", environment.server))
        rows.append(("exec cwd", environment.working_directory))
    lines = [f"  {label}: {safe_terminal_text(value)}" for label, value in rows]
    return lines if width is None else [part for line in lines for part in wrap_cells(line, width)]


def _labeled_line(label: str, value: str, width: int) -> str:
    prefix = f"  {label:<8}"
    return "\n".join(wrap_cells(prefix + safe_terminal_text(value), width))


def _tip_line(width: int) -> str:
    return "\n".join(wrap_cells("  /config settings · /resume history · /help commands", width))


def _colorize(lines: list[str]) -> list[str]:
    colored: list[str] = []
    for line in lines:
        if "AGENT" in line:
            prefix, brand = line.split("AGENT", 1)
            colored.append(
                f"{_colorize_glyphs(prefix)}{_CYAN}AGENT{brand}{_RESET}"
            )
        elif "The model organism" in line:
            prefix, tagline = line.split("The model organism", 1)
            colored.append(
                f"{_colorize_glyphs(prefix)}"
                f"{_DIM}The model organism{tagline}{_RESET}"
            )
        elif any(_glyph_color(char) for char in line):
            colored.append(_colorize_glyphs(line))
        elif line.startswith(("✦ FruitFlyAgent", "FruitFlyAgent")):
            colored.append(f"{_CYAN}{line}{_RESET}")
        elif line.startswith("  "):
            colored.append(f"{_DIM}{line}{_RESET}")
        else:
            colored.append(line)
    return colored


def _colorize_glyphs(line: str) -> str:
    """Color semantic logo glyphs without coupling layout to ANSI sequences."""
    result: list[str] = []
    active_color = ""
    for char in line:
        color = _glyph_color(char)
        if color != active_color:
            if active_color:
                result.append(_RESET)
            if color:
                result.append(color)
            active_color = color
        result.append(char)
    if active_color:
        result.append(_RESET)
    return "".join(result)


def _glyph_color(char: str) -> str:
    if "\u2801" <= char <= "\u28ff":
        return _BOLD
    return _GLYPH_COLORS.get(char, "")


__all__ = ["render_welcome"]
