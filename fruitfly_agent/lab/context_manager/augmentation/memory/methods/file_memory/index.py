"""Descriptions only; memory bodies remain available through read resources."""
from xml.sax.saxutils import escape


def render_catalog(entries, locations, *, max_chars=None):
    replaced = {key for e in entries if e['status'] == 'active' for key in e['supersedes']}
    lines = ['<available_memories>']
    pointer = ('Read the complete memory directory: ' + locations['__catalog__'] + '\n') if '__catalog__' in locations else ''
    if max_chars is not None and len(pointer) + len('<available_memories>\n</available_memories>') > max_chars:
        raise ValueError('memory budget cannot hold the complete directory reference')
    for entry in sorted(entries, key=lambda e: (e['kind'], e['id'])):
        if entry['status'] != 'active' or entry['id'] in replaced:
            continue
        item = ['<memory id="' + escape(entry['id']) + '" kind="' + entry['kind'] + '">']
        item.append('<description>' + escape(entry['description']) + '</description>')
        item.append('<location>' + escape(locations[entry['id']]) + '</location></memory>')
        if max_chars is not None and len(pointer) + len('\n'.join([*lines, *item, '</available_memories>'])) > max_chars:
            break
        lines.extend(item)
    lines.append('</available_memories>')
    return pointer + '\n'.join(lines)
