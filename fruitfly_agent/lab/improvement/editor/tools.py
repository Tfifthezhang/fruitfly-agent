"""Candidate mutation and structured submission; evidence remains read-only."""
import json
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool


def editing_tools(workspace, *, submit=None, settings=None, instructions=None, options=None):
    from .instructions import EditorInstructions
    instructions = instructions or EditorInstructions()
    from .configuration import EditorSettings
    options = EditorSettings.from_dict(options)
    async def write(ctx):
        workspace.write(ctx.args['path'],ctx.args['content'])
        return AgentToolResult(content=[TextBlock('Candidate file saved')])
    async def delete(ctx):
        workspace.delete(ctx.args['path'])
        return AgentToolResult(content=[TextBlock('Candidate file deleted')])
    async def seal(ctx):
        submit(ctx.args)
        return AgentToolResult(content=[TextBlock('Candidate validated and submitted')],terminate=True)
    tools=[AgentTool(name='write_file',label='Write candidate',description=instructions.write_file,
        parameters={'type':'object','properties':{'path':{'type':'string'},'content':{'type':'string'}},'required':['path','content']},execute=write),
        AgentTool(name='delete_file',label='Delete candidate file',description=instructions.delete_file,
        parameters={'type':'object','properties':{'path':{'type':'string'}},'required':['path']},execute=delete)]
    async def targets(ctx):
        rows=json.loads(workspace.read('context/components.json'))
        cursor,limit=ctx.args.get('cursor',0),ctx.args.get('limit',options.target_page_entries)
        if type(cursor)is not int or cursor<0 or type(limit)is not int or not 1<=limit<=options.max_target_entries:
            raise ValueError('invalid target catalog page')
        value={'targets':rows[cursor:cursor+limit], 'next_cursor':cursor+limit if cursor+limit<len(rows) else None}
        return AgentToolResult(content=[TextBlock(json.dumps(value,ensure_ascii=False))])
    async def describe(ctx):
        rows=json.loads(workspace.read('context/components.json'))
        row=next((r for r in rows if r['component_id']==ctx.args['component_id']),None)
        if row is None:raise ValueError('component is outside the resolved target set')
        from ..evidence.catalog import WorkspaceEvidence
        value=WorkspaceEvidence(workspace, settings=settings).read(row['details_path'],offset=ctx.args.get('offset',0),limit=ctx.args.get('limit'))
        return AgentToolResult(content=[TextBlock(json.dumps(value,ensure_ascii=False))])
    tools.extend((AgentTool(name='list_targets',label='Discover optimization targets',description=instructions.list_targets,
        parameters={'type':'object','properties':{'cursor':{'type':'integer'},'limit':{'type':'integer'}}},execute=targets),
        AgentTool(name='describe_target',label='Describe optimization target',description=instructions.describe_target,
        parameters={'type':'object','properties':{'component_id':{'type':'string'},'offset':{'type':'integer'},'limit':{'type':'integer'}},'required':['component_id']},execute=describe)))
    if submit is not None:
        tools.append(AgentTool(name='submit_candidate',label='Submit candidate',description=instructions.submit_candidate,
            parameters={'type':'object','properties':{'reasons':{'type':'array','items':{'type':'object','properties':{
                'component_id':{'type':'string'},'explanation':{'type':'string'},'expected_effect':{'type':'string'},'evidence_ids':{'type':'array','items':{'type':'string'}}},
                'required':['component_id','explanation','expected_effect','evidence_ids'],'additionalProperties':False}}},'required':['reasons'],'additionalProperties':False},execute=seal,requires_exclusive_batch=True))
    return tuple(tools)
