"""Strict read-only judgment submission; rejection leaves the Agent free to repair."""
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool


def normalize_no_choice(value):
    """Decode the declared empty-string sentinel without repairing other fields."""
    if isinstance(value, dict) and value.get('choice') == '':
        return {**value, 'choice': None}
    return value


def submission_tool(name, submit, *, instructions=None):
    """The same owner validator accepts tool submissions and final text responses."""
    from .instructions import EvaluatorInstructions
    instructions = instructions or EvaluatorInstructions()
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
        submit(normalize_no_choice(ctx.args))
        return AgentToolResult(content=[TextBlock('Judgment validated and retained.')], terminate=True)
    return AgentTool(name=name, label='Submit judgment', description=instructions.submit_judgment,
        parameters=schema, execute=seal, requires_exclusive_batch=True)
