"""Decode evidence formats while retaining original character coordinates."""
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class SourceRow:
    start: int
    end: int
    value: dict
    locator: str


def array_rows(text, start, locator):
    if text[start] != '[':
        raise ValueError('expected an evidence array')
    decoder, cursor = json.JSONDecoder(), start + 1
    rows: list[SourceRow] = []
    while cursor < len(text):
        while cursor < len(text) and text[cursor] in ' \t\r\n,':
            cursor += 1
        if cursor == len(text) or text[cursor] == ']':
            break
        value, end = decoder.raw_decode(text, cursor)
        if not isinstance(value, dict):
            raise ValueError('evidence array entries must be objects')
        rows.append(SourceRow(cursor, end, value, f'{locator}/{len(rows)}'))
        cursor = end
    return rows


def decode_rows(text):
    """Return rows, format and explicit gaps, including a valid JSONL prefix."""
    decoder = json.JSONDecoder()
    start = len(text) - len(text.lstrip())
    if start == len(text):
        return [], 'jsonl', []
    try:
        value, end = decoder.raw_decode(text, start)
        single = not text[end:].strip()
    except ValueError:
        value, single = None, False
    if single and isinstance(value, list):
        return array_rows(text, start, ''), 'json-array', []
    array_key = next((key for key in ('steps', 'requests') if isinstance(value, dict) and isinstance(value.get(key), list)), None)
    if single and array_key:
        cursor = start + 1
        while cursor < len(text):
            while text[cursor] in ' \r\n\t,':
                cursor += 1
            if text[cursor] == '}':
                break
            key, cursor = decoder.raw_decode(text, cursor)
            while text[cursor] in ' \r\n\t:':
                cursor += 1
            if key == array_key:
                return array_rows(text, cursor, '/' + key), 'atif' if key == 'steps' else 'model-usage', []
            _, cursor = decoder.raw_decode(text, cursor)
    rows, gaps, cursor = [], [], 0
    # splitlines() also splits valid Unicode characters inside JSON strings.
    for number, line in enumerate(text.split('\n')):
        end = cursor + len(line.rstrip('\r'))
        if line.strip():
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError('evidence record must be an object')
                rows.append(SourceRow(cursor, end, row, f'/records/{number}'))
            except ValueError as exc:
                gaps.append({'start': cursor, 'end': end, 'reason': type(exc).__name__,
                             'location': 'tail' if cursor + len(line) == len(text) else 'interior'})
        cursor += len(line) + 1
    return rows, 'jsonl', gaps
