"""Shared read-only catalog/search/read tools with precise supply receipts."""
import base64
import hashlib
import json

from fruitfly_agent.core.data_model import AgentToolResult, TextBlock, ImageBlock
from fruitfly_agent.core.data_model.media import image_type, validate_image
from fruitfly_agent.core.tool_runtime import AgentTool
from .catalog import WorkspaceEvidence
from .configuration import EvidenceSettings


def evidence_tools(workspace, *, settings=None, reader=None):
    settings = EvidenceSettings.from_dict(settings)
    reader = reader if reader is not None else WorkspaceEvidence(workspace, settings=settings)
    def allow():
        workspace.access.budget['tool_calls'] += 1
        calls = workspace.access.budget['tool_calls']
        if calls > settings.supply.max_pages:
            workspace.record('evidence-budget-exhausted', pages=calls - 1)
            return False
        return True
    def exhausted():
        return result({'status': 'budget_exhausted', 'note': 'Submit with existing citations; declare uncovered scope.'})
    def result(value):
        return AgentToolResult(content=[TextBlock(text=json.dumps(value,ensure_ascii=False))])
    async def catalog(ctx):
        if not allow():
            return exhausted()
        args=ctx.args
        if args.get('kind') == 'executions':
            from .executions import execution_page
            cursor, limit = args.get('cursor', 0), args.get('limit', settings.catalog.default_entries)
            if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= settings.catalog.max_entries:
                raise ValueError('invalid execution catalog page')
            return result(execution_page(workspace, cursor=cursor, limit=limit, status=args.get('status'), max_characters=settings.read.max_characters, compact=args.get('compact', False), run_id=args.get('run_id')))
        path=args.get('path')
        if path:
            if not path.endswith('/evidence/events.json') and path != 'evidence/events.json':
                raise ValueError('catalog.path requires a granted evidence/events.json index; browse files with catalog(prefix=...)')
            value=json.loads(workspace.read(path))
            events=[{**event, 'source_granted': (path.rsplit('/evidence/', 1)[0] + '/' + event['source_path']) in workspace.paths()}
                for event in value['events']]
            if args.get('kind'):events=[v for v in events if v['kind']==args['kind']]
            for field in ('tool_name', 'tool_call_id', 'request_id', 'operation_id', 'phase', 'status'):
                if field in args:
                    events = [v for v in events if v.get(field) == args[field]]
            if args.get('order')=='elapsed_seconds':events=sorted(events,key=lambda v:v.get('elapsed_seconds') or -1,reverse=True)
            cursor,limit=args.get('cursor',0),args.get('limit',settings.catalog.default_entries)
            if type(cursor)is not int or cursor<0 or type(limit)is not int or not 1<=limit<=settings.catalog.max_entries:
                raise ValueError('invalid event catalog page')
            return result({'path':path,'events':events[cursor:cursor+limit],'total':len(events),
                'next_cursor':cursor+limit if cursor+limit<len(events) else None,
                'note':'Navigation metadata; read source spans for semantic claims.'})
        return result(reader.catalog(prefix=args.get('prefix',''),cursor=args.get('cursor',0),limit=args.get('limit',settings.catalog.default_entries)))
    def read_granted(path):
        if path not in workspace.paths():
            workspace.access.denied(path)
            raise ValueError('read path is outside the evidence grant')
        try:
            return workspace.read(path)
        except (ValueError, KeyError, OSError):
            workspace.access.failed(path)
            raise

    async def read(ctx):
        if not allow():
            return exhausted()
        path = ctx.args['path']
        event_id = ctx.args.get('event_id')
        if event_id is not None:
            if path == 'evidence/events.json':
                prefix = ''
            elif path.endswith('/evidence/events.json'):
                prefix = path.removesuffix('evidence/events.json')
            else:
                raise ValueError('event reads require a granted evidence/events.json index')
            directory = json.loads(read_granted(path))
            event = next((entry for entry in directory['events'] if entry['event_id'] == event_id), None)
            if event is None:
                raise ValueError('event is outside the selected index')
            if 'body_path' in event:
                body_path = prefix + event['body_path']
                body = read_granted(body_path)
                if 'sha256:' + hashlib.sha256(body).hexdigest() != event['body_artifact_id']:
                    raise ValueError('event body identity mismatch')
                return result(reader.read(body_path, offset=ctx.args.get('offset', 0),
                    limit=ctx.args.get('limit', settings.read.default_characters)))
            source_path = prefix + event['source_path']
            source = read_granted(source_path)
            if 'sha256:' + hashlib.sha256(source).hexdigest() != event['artifact_id']:
                raise ValueError('event source identity mismatch')
            offset = ctx.args.get('offset', 0)
            limit = ctx.args.get('limit', settings.read.default_characters)
            length = event['end'] - event['start']
            if not 0 <= offset < length or limit < 1:
                raise ValueError('invalid event page')
            return result(reader.read(source_path, offset=event['start'] + offset,
                limit=min(limit, length - offset)))
        data=read_granted(path)
        if image_type(data) is not None:
            if workspace.access.remaining_responses(settings.supply.max_pages) <= 0:
                return exhausted()
            workspace.access.supply_responses += 1
            mime=validate_image(data)
            reference='sha256:'+hashlib.sha256(data).hexdigest()
            workspace.access.provided(path,data)
            workspace.provided_ids.add(reference)
            workspace.provided_paths.setdefault(path, set()).add(reference)
            workspace.record('evidence-image',path=path,artifact_id=reference)
            return AgentToolResult(content=[ImageBlock(data=base64.b64encode(data).decode(),media_type=mime),TextBlock(reference)])
        return result(reader.read(path,offset=ctx.args.get('offset',0),limit=ctx.args.get('limit',settings.read.default_characters)))
    async def search(ctx):
        if not allow():
            return exhausted()
        return result(reader.search(ctx.args['query'],paths=tuple(ctx.args.get('paths',())),cursor=ctx.args.get('cursor',''),limit=ctx.args.get('limit',settings.search.default_matches)))
    return (AgentTool(name='catalog',label='Browse evidence',description=settings.instructions.catalog,
        parameters={'type':'object','properties':{'run_id':{'type':'string'},'compact':{'type':'boolean'},'prefix':{'type':'string'},'path':{'type':'string'},'kind':{'type':'string'},
            **{key: {'type': 'string'} for key in ('tool_name', 'tool_call_id', 'request_id', 'operation_id', 'phase', 'status')},
            'order':{'type':'string','enum':['elapsed_seconds']},'cursor':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':settings.catalog.max_entries}},'additionalProperties':False},execute=catalog),
        AgentTool(name='read',label='Read evidence',description=settings.instructions.read,
        parameters={'type':'object','properties':{'path':{'type':'string'},'event_id':{'type':'string'},'offset':{'type':'integer'},'limit':{'type':'integer'}},'required':['path']},execute=read),
        AgentTool(name='search',label='Search evidence',description=settings.instructions.search,
        parameters={'type':'object','properties':{'query':{'type':'string'},'paths':{'type':'array','items':{'type':'string'}},'cursor':{'type':'string'},'limit':{'type':'integer','minimum':1,'maximum':settings.search.max_matches}},'required':['query'],'additionalProperties':False},execute=search))
