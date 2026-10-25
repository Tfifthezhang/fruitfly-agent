"""Single-owner POSIX line editing and permission input."""
from __future__ import annotations
import codecs
import os
import select
import threading
from dataclasses import dataclass, field
from typing import Protocol, Sequence, TextIO
from .controls import InputInterrupted, ViewAction, view_action
from .text import safe_terminal_text
from .completion import CompletionProvider, CompletionQuery, CompletionState, CompletionView

_BRACKETED_PASTE_START = b"\x1b[200~"
_BRACKETED_PASTE_END = b"\x1b[201~"

class EditorDisplay(Protocol):
    output: TextIO
    @property
    def active(self) -> bool: ...
    @property
    def copying(self) -> bool: ...
    def create_field_display(self) -> EditorDisplay: ...
    def activate(self) -> None: ...
    def suspend(self) -> None: ...
    def write(self, text: str) -> int: ...
    def set_input(self, text: str, cursor: int) -> None: ...
    def set_choices(self, labels: Sequence[str] = (), selected: int = 0) -> None: ...
    def refresh(self) -> None: ...
    def handle_action(self, action: ViewAction) -> bool: ...
    def resume_live(self) -> None: ...
    def set_completions(self, view: CompletionView) -> None: ...

@dataclass
class _InputBuffer:
    """One line's text, cursor, and temporary history navigation state."""
    history_index: int
    characters: list[str] = field(default_factory=list)
    cursor: int = 0
    draft: str = ""

    def control(self, first: bytes) -> None:
        if first == b"\x04":
            if self.cursor < len(self.characters):
                del self.characters[self.cursor]
        elif first in {b"\x7f", b"\x08"}:
            if self.cursor:
                self.cursor -= 1
                del self.characters[self.cursor]
        elif first == b"\x01":
            self.cursor = 0
        elif first == b"\x05":
            self.cursor = len(self.characters)
        elif first == b"\x15":
            del self.characters[:self.cursor]
            self.cursor = 0
        elif first == b"\x17":
            while self.cursor and self.characters[self.cursor - 1].isspace():
                self.cursor -= 1
                del self.characters[self.cursor]
            while self.cursor and not self.characters[self.cursor - 1].isspace():
                self.cursor -= 1
                del self.characters[self.cursor]

    def escape(self, sequence: bytes, descriptor: int, encoding: str, history: Sequence[str]) -> None:
        if sequence == _BRACKETED_PASTE_START:
            pasted = _decode_paste(
                _read_bracketed_paste(descriptor),
                encoding,
            )
            if pasted:
                self.characters[self.cursor:self.cursor] = pasted
                self.cursor += len(pasted)
        elif sequence in {b"\x1b[A", b"\x1bOA"} and history:
            if self.history_index == len(history):
                self.draft = "".join(self.characters)
            self.history_index = max(0, self.history_index - 1)
            self.characters = list(history[self.history_index])
            self.cursor = len(self.characters)
        elif sequence in {b"\x1b[B", b"\x1bOB"}:
            if self.history_index < len(history) - 1:
                self.history_index += 1
                self.characters = list(history[self.history_index])
            elif self.history_index == len(history) - 1:
                self.history_index = len(history)
                self.characters = list(self.draft)
            self.cursor = len(self.characters)
        elif sequence in {b"\x1b[D", b"\x1bOD"}:
            self.cursor = max(0, self.cursor - 1)
        elif sequence in {b"\x1b[C", b"\x1bOC"}:
            self.cursor = min(len(self.characters), self.cursor + 1)
        elif sequence in {b"\x1b[H", b"\x1bOH", b"\x1b[1~"}:
            self.cursor = 0
        elif sequence in {b"\x1b[F", b"\x1bOF", b"\x1b[4~"}:
            self.cursor = len(self.characters)
        elif sequence == b"\x1b[3~" and self.cursor < len(self.characters):
            del self.characters[self.cursor]


class IsolatedLineEditor:
    """POSIX non-canonical editor with persistent submission history."""

    def __init__(self, input_stream: TextIO, display: EditorDisplay) -> None:
        self.input = input_stream
        self.display = display
        self._interrupted = threading.Event()
        self._previous_terminal_state: list | None = None
        self._history: list[str] = []
        self._choices: tuple[str, ...] = ()
        self._selected_choice = 0
        self._choice_request = ""
        self._field_input = False
        self._completion: CompletionState | None = None

    def set_completion_provider(self, provider: CompletionProvider | None) -> None:
        self._completion = CompletionState(provider) if provider is not None else None
        self.display.set_completions(CompletionView())

    def _sync_completion(self, buffer: _InputBuffer) -> None:
        state = self._completion
        if state is None:
            return
        query = CompletionQuery(''.join(buffer.characters), buffer.cursor)
        if self._field_input or self._choices or self.display.copying:
            state.dismiss(query)
        else:
            state.update(query)
        self.display.set_completions(state.view)

    def _clear_completion(self) -> None:
        if self._completion is not None:
            self._completion.clear()
            self.display.set_completions(CompletionView())

    def set_choices(self, labels: Sequence[str] = (), request_id: str = "") -> None:
        self._clear_completion()
        self._choice_request = request_id
        self._choices = tuple(labels)
        self._selected_choice = 0
        self.display.set_choices(self._choices)

    def interrupt(self) -> None:
        self._interrupted.set()

    def start(self) -> None:
        """Enter no-echo character mode while preserving output processing."""

        import termios

        if self._previous_terminal_state is not None:
            return
        descriptor = self.input.fileno()
        previous = termios.tcgetattr(descriptor)
        current = previous.copy()
        current[6] = previous[6].copy()
        current[0] &= ~(
            termios.IXON | termios.ICRNL | termios.INLCR | termios.IGNCR
        )
        current[3] &= ~(
            termios.ECHO | termios.ICANON | termios.IEXTEN | termios.ISIG
        )
        current[6][termios.VMIN] = 1
        current[6][termios.VTIME] = 0
        self._previous_terminal_state = previous
        termios.tcsetattr(descriptor, termios.TCSANOW, current)
        self.display.set_input("", 0)

    def stop(self) -> None:
        """Restore the terminal mode saved by :meth:`start`."""

        import termios

        if self._previous_terminal_state is None:
            return
        descriptor = self.input.fileno()
        previous, self._previous_terminal_state = (
            self._previous_terminal_state,
            None,
        )
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)

    def read_line(self) -> str | None:
        descriptor = self.input.fileno()
        buffer = _InputBuffer(len(self._history))
        encoding = getattr(self.input, "encoding", None) or "utf-8"
        decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
        owns_terminal_state = self._previous_terminal_state is None
        try:
            if owns_terminal_state:
                self.start()
            self.display.set_input("", 0)
            while True:
                if self._interrupted.is_set():
                    self._interrupted.clear()
                    self.display.resume_live()
                    self.display.set_input("", 0)
                    raise InputInterrupted(handled=True)
                self.display.refresh()
                self._sync_completion(buffer)
                ready, _, _ = select.select([descriptor], [], [], 0.1)
                if not ready or self._interrupted.is_set():
                    continue
                first = os.read(descriptor, 1)
                if not first:
                    self.display.resume_live()
                    self.display.set_input("", 0)
                    return None
                if self._choices and first != b"\x03":
                    choice = self._read_choice(descriptor, first)
                    if choice is not None:
                        return choice
                    continue
                if first == b"\x03":
                    self.display.resume_live()
                    self.display.set_input("", 0)
                    raise InputInterrupted
                if self.display.copying and first != b"\x1b":
                    continue
                if first == b'\t' and self._completion is not None and not self._field_input:
                    query = CompletionQuery(''.join(buffer.characters), buffer.cursor)
                    accepted = self._completion.accept(query)
                    if accepted is not None:
                        buffer.characters, buffer.cursor = list(accepted.text), accepted.cursor
                        self.display.set_completions(self._completion.view)
                        self.display.set_input(accepted.text, accepted.cursor)
                    continue
                if first in {b"\r", b"\n"}:
                    value = "".join(buffer.characters)
                    if value and (not self._history or self._history[-1] != value):
                        self._history.append(value)
                    self.display.set_input("", 0)
                    return value
                if first == b"\x04" and not buffer.characters:
                    self.display.set_input("", 0)
                    return None
                if first == b"\x1b":
                    sequence = _read_escape_sequence(descriptor, first)
                    action = view_action(sequence)
                    if action is not None and self.display.handle_action(action):
                        if self._completion is not None:
                            self._completion.dismiss(CompletionQuery(''.join(buffer.characters), buffer.cursor))
                            self.display.set_completions(CompletionView())
                        continue
                    if self.display.copying:
                        if sequence == _BRACKETED_PASTE_START:
                            _read_bracketed_paste(descriptor)
                        continue
                    if sequence.startswith(b'\x1b[<'):
                        continue
                    if self._field_input and sequence == b'\x1b':
                        raise InputInterrupted
                    if self._completion is not None and self._completion.view.items:
                        if sequence == b'\x1b':
                            self._completion.dismiss(CompletionQuery(''.join(buffer.characters), buffer.cursor))
                            self.display.set_completions(CompletionView())
                            continue
                        if sequence in {b'\x1b[A', b'\x1bOA', b'\x1b[B', b'\x1bOB'}:
                            self._completion.move(-1 if sequence.endswith(b'A') else 1)
                            self.display.set_completions(self._completion.view)
                            continue
                    buffer.escape(sequence, descriptor, encoding, self._history)
                elif first in {b"\x04", b"\x7f", b"\x08", b"\x01", b"\x05", b"\x15", b"\x17"}:
                    buffer.control(first)
                else:
                    decoded = decoder.decode(first, final=False)
                    for character in decoded:
                        if character.isprintable():
                            buffer.characters.insert(buffer.cursor, character)
                            buffer.cursor += 1
                self.display.set_input("".join(buffer.characters), buffer.cursor)
        finally:
            self._clear_completion()
            if owns_terminal_state:
                self.stop()

    def read_field_line(self, label: str) -> str | None:
        """Borrow this reader for a visible form while the chat display is suspended."""
        if self.display.active:
            raise RuntimeError('suspend the chat display before reading a form field')
        previous = self.display, self._history, self._choices, self._field_input
        owns_terminal_state = self._previous_terminal_state is None
        display = self.display.create_field_display()
        self.display, self._history, self._choices = display, [], ()
        self._field_input = True
        try:
            display.write(safe_terminal_text(label) + '\n')
            self.start()
            display.activate()
            return self.read_line()
        finally:
            try:
                display.suspend()
            finally:
                try:
                    if owns_terminal_state:
                        self.stop()
                finally:
                    self.display, self._history, self._choices, self._field_input = previous

    def _read_choice(self, descriptor: int, first: bytes) -> str | None:
        """Consume a permission-selection key without changing the prompt buffer."""
        if first in {b"\r", b"\n"}:
            return "\x00authorize:" + self._choice_request + ":" + str(self._selected_choice + 1)
        if first in {b"1", b"2", b"3"}:
            return "\x00authorize:" + self._choice_request + ":" + first.decode()
        if first == b"\x1b":
            sequence = _read_escape_sequence(descriptor, first)
            if sequence == b"\x1b":
                return "\x00authorize:" + self._choice_request + ":3"
            if sequence in {b"\x1b[A", b"\x1b[B", b"\x1bOA", b"\x1bOB"}:
                self._selected_choice = (self._selected_choice + (-1 if sequence.endswith(b"A") else 1)) % len(self._choices)
        self.display.set_choices(self._choices, self._selected_choice)
        return None


def _read_escape_sequence(descriptor: int, first: bytes) -> bytes:
    sequence = first
    while len(sequence) < 32 and select.select([descriptor], [], [], 0.02)[0]:
        sequence += os.read(descriptor, 1)
        if sequence != b"\x1bO" and sequence[-1:] in b"~ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
            break
    return sequence


def _read_bracketed_paste(descriptor: int) -> bytes:
    """Read paste payload without consuming the following submit key."""

    payload = bytearray()
    while True:
        chunk = os.read(descriptor, 1)
        if not chunk:
            return bytes(payload)
        payload.extend(chunk)
        if payload.endswith(_BRACKETED_PASTE_END):
            del payload[-len(_BRACKETED_PASTE_END) :]
            return bytes(payload)


def _decode_paste(payload: bytes, encoding: str) -> str:
    """Normalize clipboard line endings and drop terminal control bytes."""

    text = payload.decode(encoding, errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(
        character
        for character in text
        if character in {"\n", "\t"} or character.isprintable()
    )


