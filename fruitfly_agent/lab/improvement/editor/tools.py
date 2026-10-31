"""Candidate mutation and structured submission; evidence remains read-only."""
import json
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool


def editing_tools(workspace, *, submit=None):
    async def write(ctx):
        workspace.write(ctx.args['path'],ctx.args['content'])
        return AgentToolResult(content=[TextBlock('Candidate file saved')])
    async def delete(ctx):
        workspace.delete(ctx.args['path'])
        return AgentToolResult(content=[TextBlock('Candidate file deleted')])
    async def seal(ctx):
        submit(ctx.args)
        return AgentToolResult(content=[TextBlock('Candidate validated and submitted')],terminate=True)
    tools=[AgentTool(name='write_file',label='Write candidate',description='Replace a complete UTF-8 file in a granted candidate component.',
        parameters={'type':'object','properties':{'path':{'type':'string'},'content':{'type':'string'}},'required':['path','content']},execute=write),
        AgentTool(name='delete_file',label='Delete candidate file',description='Delete a file in a granted candidate component.',
        parameters={'type':'object','properties':{'path':{'type':'string'}},'required':['path']},execute=delete)]
    async def targets(ctx):
        rows=json.loads(workspace.read('context/components.json'))
        cursor,limit=ctx.args.get('cursor',0),ctx.args.get('limit',20)
        if type(cursor)is not int or cursor<0 or type(limit)is not int or not 1<=limit<=100:
            raise ValueError('invalid target catalog page')
        value={'targets':rows[cursor:cursor+limit], 'next_cursor':cursor+limit if cursor+limit<len(rows) else None}
        return AgentToolResult(content=[TextBlock(json.dumps(value,ensure_ascii=False))])
    async def describe(ctx):
        rows=json.loads(workspace.read('context/components.json'))
        row=next((r for r in rows if r['component_id']==ctx.args['component_id']),None)
        if row is None:raise ValueError('component is outside the resolved target set')
        from ..evidence.catalog import WorkspaceEvidence
        value=WorkspaceEvidence(workspace).read(row['details_path'],offset=ctx.args.get('offset',0),limit=ctx.args.get('limit',12000))
        return AgentToolResult(content=[TextBlock(json.dumps(value,ensure_ascii=False))])
    tools.extend((AgentTool(name='list_targets',label='Discover optimization targets',description='Page the frozen legal target index. Details are loaded only when requested.',
        parameters={'type':'object','properties':{'cursor':{'type':'integer'},'limit':{'type':'integer'}}},execute=targets),
        AgentTool(name='describe_target',label='Describe optimization target',description='Read a page of owner-authored field meanings, current/default values, units and constraints.',
        parameters={'type':'object','properties':{'component_id':{'type':'string'},'offset':{'type':'integer'},'limit':{'type':'integer'}},'required':['component_id']},execute=describe)))
    if submit is not None:
        tools.append(AgentTool(name='submit_candidate',label='Submit candidate',description='Validate the candidate and evidence-grounded behavior hypotheses. Ends this editing invocation on success.',
            parameters={'type':'object','properties':{'reasons':{'type':'array','items':{'type':'object','properties':{
                'component_id':{'type':'string'},'explanation':{'type':'string'},'expected_effect':{'type':'string'},'evidence_ids':{'type':'array','items':{'type':'string'}}},
                'required':['component_id','explanation','expected_effect','evidence_ids'],'additionalProperties':False}}},'required':['reasons'],'additionalProperties':False},execute=seal,requires_exclusive_batch=True))
    return tuple(tools)
