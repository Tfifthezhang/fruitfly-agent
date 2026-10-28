"""One session's public source messages and immutable reduction artifacts."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from dataclasses import dataclass

from fruitfly_agent.core.data_model import TextBlock, ToolCallBlock, ImageBlock, CustomMessage


@dataclass(frozen=True)
class HistoryConfig:
    max_artifact_bytes: int = 16_000_000

    def __post_init__(self):
        if type(self.max_artifact_bytes) is not int or not 1024 <= self.max_artifact_bytes <= 64_000_000:
            raise ValueError('max_artifact_bytes must be an integer within [1024, 64000000]')


def public_message(message):
    if isinstance(message, CustomMessage):
        return '[' + message.kind + '] ' + message.text
    content = message.content
    if isinstance(content, str):
        return message.role + ': ' + content
    parts = []
    for block in content:
        if isinstance(block, TextBlock): parts.append(block.text)
        elif isinstance(block, ToolCallBlock):
            parts.append('tool call ' + block.id + ' ' + block.name + ' ' + json.dumps(block.input, ensure_ascii=False))
        elif isinstance(block, ImageBlock): parts.append('[Image ' + block.media_type + '; inspect the original image before inferring its contents]')
    label = message.role + (' ' + message.tool_call_id + ' error=' + str(message.is_error) if hasattr(message, 'tool_call_id') else '')
    return label + ': ' + '\n'.join(parts)


class SessionHistory:
    def __init__(self, root=None, *, session=None, config=None):
        self.config = config or HistoryConfig()
        self.root = Path(root) if root is not None else None
        self.session = session
        self.values = {}
        self.sources = {}
        if session is not None:
            self.bind(session.context_items())

    def bind(self, items):
        self.sources = {item.id: public_message(item.message) for item in items}

    def checkpoint(self, mechanism):
        state = None
        if self.session is not None:
            for entry in self.session.read_all():
                if (entry.type == 'compaction' or entry.type == 'meta' and entry.payload.get('kind') == 'context_state'):
                    if entry.payload.get('mechanismId') == mechanism and 'state' in entry.payload:
                        state = entry.payload['state']
        return state

    def text(self, reference):
        return self._bytes(reference).decode()

    def put(self, text):
        if not isinstance(text, str) or len(text.encode()) > self.config.max_artifact_bytes:
            raise ValueError('context artifact exceeds max_artifact_bytes')
        data = text.encode()
        reference = 'sha256:' + hashlib.sha256(data).hexdigest()
        if self.root is None:
            self.values[reference] = data
        else:
            if self.root.is_symlink():
                raise ValueError('context artifact root cannot be a symlink')
            self.root.mkdir(parents=True, exist_ok=True)
            path = self.root / (reference[7:] + '.txt')
            if path.is_symlink():
                raise ValueError('context artifacts cannot be symlinks')
            if not path.exists():
                fd, name = tempfile.mkstemp(prefix='.context-', dir=self.root)
                try:
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(data); stream.flush(); os.fsync(stream.fileno())
                    os.replace(name, path)
                finally:
                    Path(name).unlink(missing_ok=True)
            self._bytes(reference)
        return reference

    def _bytes(self, reference):
        if not isinstance(reference, str) or len(reference) != 71 or not reference.startswith('sha256:') or any(c not in '0123456789abcdef' for c in reference[7:]):
            raise ValueError('context artifact needs a SHA-256 reference')
        if self.root is None:
            data = self.values[reference]
        else:
            if self.root.is_symlink():
                raise ValueError('context artifact root cannot be a symlink')
            path = self.root / (reference[7:] + '.txt')
            if path.is_symlink(): raise ValueError('context artifacts cannot be symlinks')
            if path.stat().st_size > self.config.max_artifact_bytes:
                raise ValueError('context artifact exceeds its byte bound')
            data = path.read_bytes()
        if 'sha256:' + hashlib.sha256(data).hexdigest() != reference:
            raise ValueError('context artifact identity mismatch')
        return data

    def read(self, reference, *, offset=0, limit=12000):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 24000:
            raise ValueError('context reads require bounded character offsets/limits')
        if self.session is not None:
            self.bind(self.session.context_items())
        text = self.sources[reference] if reference in self.sources else self.text(reference)
        result = text[offset:offset + limit]
        if offset + limit < len(text): result += '\n[Continue at offset=' + str(offset + limit) + ']'
        return result

    def search(self, query, *, limit=20):
        if not isinstance(query, str) or not 1 <= len(query) <= 500 or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('context search needs bounded query and result count')
        result = []
        if self.session is not None:
            self.bind(self.session.context_items())
        for reference, text in self.sources.items():
            offset = text.find(query)
            if offset >= 0:
                result.append({'reference': reference, 'offset': offset,
                    'text': text[max(0, offset - 80):offset + min(160, len(query)) + 80]})
                if len(result) >= limit: break
        return result

    def validate_state(self, state):
        if not isinstance(state, dict): raise ValueError('context checkpoint must be a mapping')
        for value in state.values():
            if isinstance(value, dict) and 'artifact' in value:
                self._bytes(value['artifact'])

    def validate_recovery(self, messages):
        import re
        for message in messages:
            if isinstance(message, CustomMessage):
                for reference in re.findall(r'\[Context artifact (sha256:[a-f0-9]{64})\]', message.text):
                    self._bytes(reference)
