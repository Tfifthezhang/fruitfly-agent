"""Bounded local clipboard image access; never reads terminal input."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from fruitfly_agent.core.data_model import ImageBlock, encode_image_bytes
from fruitfly_agent.core.data_model.media import MAX_IMAGE_BYTES, validate_image


def read_clipboard_image() -> ImageBlock | None:
    try:
        return _read_image()
    except subprocess.TimeoutExpired as exc:
        raise ValueError("clipboard image read timed out") from exc


def _read_image() -> ImageBlock | None:
    with tempfile.TemporaryDirectory(prefix='fruitfly-clipboard-') as directory:
        path = Path(directory) / 'image.png'
        if sys.platform == 'darwin' and shutil.which('osascript'):
            quoted = json.dumps(str(path))
            script = ('set imageData to the clipboard as «class PNGf»\n'
                      'set outputFile to open for access POSIX file ' + quoted + ' with write permission\n'
                      'try\nset eof outputFile to 0\nwrite imageData to outputFile\n'
                      'on error errorMessage\nclose access outputFile\nerror errorMessage\nend try\n'
                      'close access outputFile')
            result = subprocess.run(['osascript', '-e', script], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=False)
        else:
            command = (['wl-paste', '--no-newline', '--type', 'image/png'] if shutil.which('wl-paste') else
                       ['xclip', '-selection', 'clipboard', '-t', 'image/png', '-o'] if shutil.which('xclip') else None)
            if command is None:
                return None
            with path.open('wb') as stream:
                result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stream,
                                        stderr=subprocess.DEVNULL, timeout=3, check=False)
        if result.returncode or not path.is_file():
            return None
        with path.open('rb') as stream:
            data = stream.read(MAX_IMAGE_BYTES + 1)
        return encode_image_bytes(data, validate_image(data))
