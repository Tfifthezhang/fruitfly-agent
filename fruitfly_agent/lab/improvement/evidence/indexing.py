"""Rebuildable navigation derived from immutable execution resources; no model."""
from dataclasses import asdict, replace
import json

from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_agent.improvement.execution.facts import read_facts

OVERVIEW_PATH = 'evidence/overview.json'
EVENTS_PATH = 'evidence/events.json'


def organize_evidence(task, record, artifacts):
    if any(r.path == OVERVIEW_PATH for r in record.artifacts):
        return record
    facts = read_facts(record, artifacts)
    sources, events = [], []
    for resource in record.artifacts:
        source = {'path':resource.path, 'artifact_id':resource.artifact_id, 'kind':resource.kind}
        sources.append(source)
        if resource.kind != 'trajectory':
            continue
        try:
            text = artifacts.read(resource.artifact_id).decode('utf-8')
        except (ValueError, KeyError, OSError, UnicodeError) as exc:
            source.update(status='unavailable', reason=type(exc).__name__)
            continue
        try:
            if text.lstrip().startswith('['):
                decoder, cursor = json.JSONDecoder(), text.index('[')+1
                rows=[]
                while cursor<len(text):
                    while cursor<len(text) and (text[cursor].isspace() or text[cursor]==','):cursor+=1
                    if cursor>=len(text) or text[cursor]==']':break
                    value,end=decoder.raw_decode(text,cursor)
                    rows.append((cursor,end,value));cursor=end
            else:
                rows=[]
                cursor=0
                for line in text.splitlines(keepends=True):
                    if line.strip():rows.append((cursor,cursor+len(line.rstrip('\r\n')),json.loads(line)))
                    cursor+=len(line)
        except (ValueError, TypeError) as exc:
            source.update(status='unindexed', reason=type(exc).__name__)
            continue
        source['status']='indexed'
        for start,end,row in rows:
            if not isinstance(row,dict):continue
            payload = row.get('payload', row.get('data', row))
            if 'payload_json' in row:
                try:
                    payload = json.loads(row['payload_json'])
                except (ValueError, TypeError):
                    payload = {}
            if not isinstance(payload, dict):
                payload = {}
            message=row.get('message', payload.get('message', payload))
            if not isinstance(message,dict):message={}
            data=payload
            kind=row.get('event') or row.get('kind') or message.get('role') or row.get('type','event')
            events.append({'event_id':content_hash(canonical_json([resource.artifact_id,start,end])),
                'kind':kind,'source_path':resource.path,'artifact_id':resource.artifact_id,'start':start,'end':end,
                'timestamp':row.get('timestamp'), 'elapsed_seconds':data.get('elapsed_seconds'),
                'tool_name':data.get('tool_name',message.get('toolName',message.get('tool_name'))),
                'is_error':message.get('isError',message.get('is_error',data.get('is_error'))),
                'status':data.get('status')})
    identity=content_hash(canonical_json({'run_id':record.run_id,'sources':sources}))
    event_index={'run_id':record.run_id,'source_identity':identity,'events':events,'sources':sources,
        'complete':facts.complete if facts is not None else False}
    overview={'run_id':record.run_id,'task':task.instruction,'status':record.status,
        'source_identity':identity,'output_id':artifacts.put(record.output.encode()),
        'output_characters':len(record.output),'output_excerpt':record.output[:2000],
        'termination_reason':facts.termination_reason if facts is not None else 'unknown',
        'elapsed_seconds':facts.elapsed_seconds if facts is not None else None,
        'usage':asdict(facts)['usage'] if facts is not None else [],
        'counters':dict(facts.counters) if facts is not None else {},
        'deliverables':[asdict(r) for r in record.artifacts if r.kind=='deliverable'],
        'event_count':len(events),'events_path':EVENTS_PATH,'sources':sources,
        'complete':facts.complete if facts is not None else False}
    resources=tuple(Resource(path,artifacts.put(canonical_json(value).encode()),'application/json','diagnostic')
        for path,value in ((OVERVIEW_PATH,overview),(EVENTS_PATH,event_index)))
    return replace(record,artifacts=(*record.artifacts,*resources))
