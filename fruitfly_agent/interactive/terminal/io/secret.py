"""Echo-suppressed input shared by terminal forms; never enters line history."""
import termios
import os
import select
from .controls import InputEnded, InputInterrupted
from typing import TextIO

def read_secret(input_stream: TextIO, output_stream: TextIO, *, prompt: str = "API key (hidden; blank reuses an existing key): ") -> str | None:
    """Bypass readline/history and disable TTY echo, restoring it on every exit."""
    descriptor = input_stream.fileno() if input_stream.isatty() else None
    original = termios.tcgetattr(descriptor) if descriptor is not None else None
    try:
        if original is not None:
            assert descriptor is not None
            hidden = list(original)
            hidden[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG)
            hidden[6] = list(original[6])
            hidden[6][termios.VMIN] = 1
            hidden[6][termios.VTIME] = 0
            termios.tcsetattr(descriptor, termios.TCSANOW, hidden)
        output_stream.write(prompt)
        output_stream.flush()
        if descriptor is not None:
            value = bytearray()
            while True:
                char = os.read(descriptor, 1)
                if not char or char == b'\x04':
                    raise InputEnded
                if char in (b'\x03', b'\x1b'):
                    if char == b'\x1b':
                        while select.select([descriptor], [], [], .02)[0]:
                            os.read(descriptor, 1)
                    raise InputInterrupted
                if char in (b'\r', b'\n'):
                    return value.decode('utf-8')
                if char in (b'\x7f', b'\x08'):
                    if value:
                        start = len(value) - 1
                        while start > 0 and value[start] & 0xc0 == 0x80:
                            start -= 1
                        del value[start:]
                    continue
                value.extend(char)
        line = input_stream.readline()
        if line == "":
            raise InputEnded
        return line.rstrip("\r\n")
    finally:
        if original is not None:
            assert descriptor is not None
            termios.tcsetattr(descriptor, termios.TCSADRAIN, original)
        output_stream.write("\n")
        output_stream.flush()


