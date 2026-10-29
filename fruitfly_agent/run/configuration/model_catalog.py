"""Reorder model fields without rewriting values, comments or unrelated catalog text."""
from __future__ import annotations

import yaml
from yaml.nodes import MappingNode, Node, SequenceNode

from fruitfly_agent.providers.specs import MODEL_FIELD_ORDER, ordered_model_entry


def _content_end(node: Node, seen: frozenset[int] = frozenset()) -> int:
    if id(node) in seen:
        return node.start_mark.index
    seen = seen | {id(node)}
    if isinstance(node, MappingNode) and not node.flow_style and node.value:
        return max(_content_end(part, seen) for pair in node.value for part in pair)
    if isinstance(node, SequenceNode) and not node.flow_style and node.value:
        return max(_content_end(part, seen) for part in node.value)
    return node.end_mark.index


def order_model_catalog(text: str) -> str:
    """Use setup field order, retaining authored text and checking semantic equality."""
    if not text.strip():
        return text
    root = yaml.compose(text)
    original = yaml.safe_load(text)
    if not isinstance(root, MappingNode) or not isinstance(original, dict):
        raise ValueError('model catalog must be a YAML mapping')
    models = next((value for key, value in root.value if key.value == 'models'), None)
    if not isinstance(models, MappingNode):
        raise ValueError('model catalog must contain a models mapping')
    if len({key.value for key, _ in root.value}) != len(root.value) or len({key.value for key, _ in models.value}) != len(models.value):
        raise ValueError('model catalog requires distinct keys')
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    def end_line(index: int) -> int:
        if index and text[index - 1] == '\n':
            return index
        end = text.find('\n', index)
        return len(text) if end < 0 else end + 1

    edits = []
    for alias, entry in models.value:
        if not isinstance(entry, MappingNode):
            raise ValueError('model entry must be a mapping')
        if len({key.value for key, _ in entry.value}) != len(entry.value):
            raise ValueError('model entry requires distinct field names')
        raw = original['models'][alias.value]
        ordered = ordered_model_entry(raw)
        if list(raw) == list(ordered):
            continue
        if entry.flow_style:
            parts = {}
            for key, value in entry.value:
                parts[key.value] = text[key.start_mark.index:value.end_mark.index]
            # Comments between flow entries cannot be assigned to a field reliably.
            boundaries = [entry.start_mark.index + 1, *[value.end_mark.index for _, value in entry.value]]
            starts = [*[key.start_mark.index for key, _ in entry.value], entry.end_mark.index - 1]
            if any('#' in text[left:right] for left, right in zip(boundaries, starts)):
                raise ValueError('expand commented flow model entries to block mappings before reordering')
            edits.append((entry.start_mark.index, entry.end_mark.index,
                          '{' + ', '.join(parts[name] for name in ordered) + '}'))
            continue
        starts = []
        lower = offsets[alias.start_mark.line + 1]
        for key, value in entry.value:
            line = key.start_mark.line
            while line > 0 and offsets[line - 1] >= lower:
                prior = lines[line - 1]
                indent = len(prior) - len(prior.lstrip(' '))
                if prior.strip() and not (prior.lstrip().startswith('#') and indent == key.start_mark.column):
                    break
                line -= 1
            starts.append(offsets[line])
            lower = end_line(max(key.end_mark.index, _content_end(value)))
        end = end_line(max(entry.value[-1][0].end_mark.index, _content_end(entry.value[-1][1])))
        chunks = {key.value: text[start:stop] for (key, _), start, stop in
                  zip(entry.value, starts, [*starts[1:], end])}
        pieces = [chunks[name] for name in MODEL_FIELD_ORDER if name in chunks]
        newline = '\r\n' if '\r\n' in text else '\n'
        replacement = ''.join(part + (newline if index < len(pieces) - 1 and not part.endswith('\n') else '')
                              for index, part in enumerate(pieces))
        edits.append((starts[0], end, replacement))
    result = text
    for start, end, replacement in sorted(edits, reverse=True):
        result = result[:start] + replacement + result[end:]
    try:
        unchanged = yaml.safe_load(result) == original
    except yaml.YAMLError as exc:
        raise ValueError('cannot safely reorder this model catalog') from exc
    if not unchanged:
        raise ValueError('model field ordering changed catalog values')
    return result
