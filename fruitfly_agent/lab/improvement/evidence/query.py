"""Bounded literal queries over granted text, with attributable source offsets."""


def search_text(text, query, *, offset=0, limit=20):
    if not isinstance(query, str) or not 1 <= len(query) <= 500:
        raise ValueError('query must contain 1–500 characters')
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('search needs a nonnegative offset and limit 1–50')
    matches: list[dict[str, int | str]] = []
    returned = 0
    cursor = min(offset, len(text))
    while len(matches) < limit:
        found = text.find(query, cursor)
        if found < 0:
            return {'matches': matches, 'next_offset': None, 'characters': len(text)}
        excerpt = text[max(0, found - 80):found + len(query) + 160]
        if returned + len(excerpt) > 12000:
            return {'matches': matches, 'next_offset': found, 'characters': len(text)}
        matches.append({'offset': found, 'text': excerpt})
        returned += len(excerpt)
        cursor = found + len(query)
    return {'matches': matches, 'next_offset': cursor, 'characters': len(text)}
