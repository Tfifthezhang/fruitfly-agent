"""Shared read-only catalog/search/read tools with precise supply receipts."""
import base64
import hashlib
import json

from fruitfly_agent.core.data_model import AgentToolResult, TextBlock, ImageBlock
from fruitfly_agent.core.data_model.media import image_type, validate_image
from fruitfly_agent.core.tool_runtime import AgentTool
from .catalog import WorkspaceEvidence


def evidence_tools(workspace, *, page_characters=12000, reader=None):
    reader = reader if reader is not None else WorkspaceEvidence(workspace, page_characters=page_characters)
    def result(value):
        return AgentToolResult(content=[TextBlock(text=json.dumps(value,ensure_ascii=False))])
    async def catalog(ctx):
        args=ctx.args
        path=args.get('path')
        if path:
            if not path.endswith('/evidence/events.json') and path != 'evidence/events.json':
                raise ValueError('event catalog requires a granted event index')
            value=json.loads(workspace.read(path))
            events=value['events']
            if args.get('kind'):events=[v for v in events if v['kind']==args['kind']]
            if args.get('order')=='elapsed_seconds':events=sorted(events,key=lambda v:v.get('elapsed_seconds') or -1,reverse=True)
            cursor,limit=args.get('cursor',0),args.get('limit',50)
            if type(cursor)is not int or cursor<0 or type(limit)is not int or not 1<=limit<=100:
                raise ValueError('invalid event catalog page')
            return result({'path':path,'events':events[cursor:cursor+limit],'total':len(events),
                'next_cursor':cursor+limit if cursor+limit<len(events) else None,
                'note':'Navigation metadata; read source spans for semantic claims.'})
        return result(reader.catalog(prefix=args.get('prefix',''),cursor=args.get('cursor',0),limit=args.get('limit',50)))
    async def read(ctx):
        path=ctx.args['path']
        data=workspace.read(path)
        if image_type(data) is not None:
            mime=validate_image(data)
            reference='sha256:'+hashlib.sha256(data).hexdigest()
            workspace.access.provided(path,data)
            workspace.provided_ids.add(reference)
            workspace.record('evidence-image',path=path,artifact_id=reference)
            return AgentToolResult(content=[ImageBlock(data=base64.b64encode(data).decode(),media_type=mime),TextBlock(reference)])
        return result(reader.read(path,offset=ctx.args.get('offset',0),limit=ctx.args.get('limit',page_characters)))
    async def search(ctx):
        return result(reader.search(ctx.args['query'],paths=tuple(ctx.args.get('paths',())),cursor=ctx.args.get('cursor',''),limit=ctx.args.get('limit',20)))
    return (AgentTool(name='catalog',label='Browse evidence',description='Page granted files or an event index. Overview and event indexes navigate to immutable originals.',
        parameters={'type':'object','properties':{'prefix':{'type':'string'},'path':{'type':'string'},'kind':{'type':'string'},'order':{'type':'string','enum':['elapsed_seconds']},'cursor':{'type':'integer'},'limit':{'type':'integer'}}},execute=catalog),
        AgentTool(name='read',label='Read evidence',description='Read a granted original page or image. Cite the returned citation_id; continue with next_offset. Offsets are source characters.',
        parameters={'type':'object','properties':{'path':{'type':'string'},'offset':{'type':'integer'},'limit':{'type':'integer'}},'required':['path']},execute=read),
        AgentTool(name='search',label='Search evidence',description='Literal search across granted files or selected paths. Returns source spans, citation IDs, failures and a continuation cursor.',
        parameters={'type':'object','properties':{'query':{'type':'string'},'paths':{'type':'array','items':{'type':'string'}},'cursor':{'type':'string'},'limit':{'type':'integer'}},'required':['query']},execute=search))
