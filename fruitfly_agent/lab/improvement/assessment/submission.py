"""Strict read-only judgment submission; rejection leaves the Agent free to repair."""
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool


def submission_tool(name, submit):
    """The same owner validator accepts tool submissions and final text responses."""
    text = {'type': 'string'}
    citations = {'type': 'array', 'items': text}
    def obj(fields):
        return {'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False}
    dimension = obj({'dimension': text, 'criterion': text,
        'judgment': {'type': 'string', 'enum': ['met', 'partial', 'unmet', 'unknown']},
        'reason': text, 'uncertainty': text, 'evidence_ids': citations})
    finding = obj({'kind': {'type': 'string', 'enum': ['process', 'hypothesis', 'direction']},
        'subject': text, 'observation': text, 'uncertainty': text, 'evidence_ids': citations})
    row = obj({'run_id': text, 'dimensions': {'type': 'array', 'items': dimension},
        'findings': {'type': 'array', 'items': finding}})
    schema = obj({'evaluations': {'type': 'array', 'items': row},
        'choice': {'type': 'string', 'description': 'Existing run ID, or empty string for no choice.'}, 'reason': text, 'uncertainty': text, 'evidence_ids': citations})
    async def seal(ctx):
        submit({**ctx.args, 'choice': ctx.args.get('choice') or None})
        return AgentToolResult(content=[TextBlock('Judgment validated and retained.')], terminate=True)
    return AgentTool(name=name, label='Submit judgment', description=(
        'Submit the complete judgment. The host checks identities, structure and supplied citations. '
        'Correct any reported validation errors and resubmit; success finishes this invocation.'),
        parameters=schema, execute=seal, requires_exclusive_batch=True)
