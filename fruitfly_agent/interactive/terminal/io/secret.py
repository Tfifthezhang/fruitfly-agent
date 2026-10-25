"""Echo-suppressed input shared by terminal forms; never enters line history."""
import termios
from typing import TextIO

def read_secret(input_stream: TextIO, output_stream: TextIO, *, prompt: str = "API key (hidden; blank reuses an existing key): ") -> str | None:
    """Bypass readline/history and disable TTY echo, restoring it on every exit."""
    descriptor = input_stream.fileno() if input_stream.isatty() else None
    original = termios.tcgetattr(descriptor) if descriptor is not None else None
    try:
        if original is not None:
            assert descriptor is not None
            hidden = list(original)
            hidden[3] &= ~(termios.ECHO | termios.ECHONL)
            termios.tcsetattr(descriptor, termios.TCSANOW, hidden)
        output_stream.write(prompt)
        output_stream.flush()
        line = input_stream.readline()
        return None if line == "" else line.rstrip("\r\n")
    finally:
        if original is not None:
            assert descriptor is not None
            termios.tcsetattr(descriptor, termios.TCSADRAIN, original)
        output_stream.write("\n")
        output_stream.flush()


