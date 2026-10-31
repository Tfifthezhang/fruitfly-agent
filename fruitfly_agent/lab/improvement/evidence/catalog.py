"""Paged catalog and literal retrieval over exactly one granted workspace."""
import hashlib
import json
from dataclasses import asdict

from fruitfly_agent.core.data_model.media import decode_text_file
from fruitfly_agent.improvement.contracts.evidence import EvidenceSpan


class WorkspaceEvidence:
    def __init__(self, workspace, *, page_characters=12000):
        self.workspace, self.page_characters = workspace, page_characters

    def catalog(self, *, prefix='', cursor=0, limit=50):
        if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('catalog needs a nonnegative cursor and page size 1..100')
        paths = tuple(p for p in self.workspace.paths() if p.startswith(prefix))
        return {'files': list(paths[cursor:cursor+limit]), 'total': len(paths),
            'next_cursor': cursor+limit if cursor+limit < len(paths) else None}

    def read(self, path, *, offset=0, limit=12000):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 24000:
            raise ValueError('read needs a nonnegative offset and page size 1..24000')
        self.workspace.access.grant(self.workspace.paths())
        try:
            data = self.workspace.read(path)
            text = decode_text_file(data)
        except (ValueError, KeyError, OSError):
            self.workspace.access.failed(path)
            raise
        reference = 'sha256:' + hashlib.sha256(data).hexdigest()
        start, end = min(offset, len(text)), min(offset+limit, len(text))
        span = EvidenceSpan(reference, start, end)
        page = text[start:end]
        if page or not text:
            self.workspace.access.provided(path, page, offset=start)
            self.workspace.provided_ids.add(span.citation_id)
        value = {'path': path, 'artifact_id': reference, 'citation_id': span.citation_id,
            'start': start, 'end': end, 'characters': len(text), 'text': page,
            'status': 'text', 'next_offset': end if end < len(text) else None}
        self.workspace.record('evidence-page', **{k:v for k,v in value.items() if k!='text'})
        return value

    def search(self, query, *, paths=(), cursor='', limit=20):
        if not isinstance(query, str) or not 1 <= len(query) <= 500 or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('search requires literal query and page size 1..50')
        available = self.workspace.paths()
        selected = tuple(sorted(paths or (p for p in available if not p.startswith('harness/'))))
        if set(selected) - set(available):
            raise ValueError('search path is outside the evidence grant')
        scope = hashlib.sha256(json.dumps([query, selected], separators=(',', ':')).encode()).hexdigest()
        index, offset = 0, 0
        if cursor:
            value = json.loads(cursor)
            if set(value) != {'scope','file','offset'} or value['scope'] != scope:
                raise ValueError('search cursor differs from query scope')
            index, offset = value['file'], value['offset']
            if type(index) is not int or type(offset) is not int or not 0 <= index <= len(selected) or offset < 0:
                raise ValueError('invalid search cursor')
        matches: list[dict] = []
        unavailable: list[dict] = []
        characters = 0
        while index < len(selected):
            path = selected[index]
            try:
                text = decode_text_file(self.workspace.read(path))
            except (ValueError, KeyError, OSError) as exc:
                unavailable.append({'path':path, 'status':type(exc).__name__})
                index, offset = index+1, 0
                continue
            found = text.find(query, offset)
            if found < 0:
                index, offset = index+1, 0
                continue
            start, end = max(0, found-80), min(len(text), found+len(query)+160)
            if matches and (len(matches) >= limit or characters + end-start > 12000):
                break
            match = self.read(path, offset=start, limit=max(1,end-start))
            match['match_offset'] = found
            matches.append(match)
            characters += end-start
            offset = found+len(query)
        next_cursor = json.dumps({'scope':scope,'file':index,'offset':offset}) if index<len(selected) else None
        return {'matches':matches, 'unavailable':unavailable, 'next_cursor':next_cursor, 'complete':next_cursor is None}
