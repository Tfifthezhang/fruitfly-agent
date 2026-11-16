"""Submit durable JSON through an injected owner's existing validator."""
import json
import inspect
from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.core.data_model import AgentToolResult, TextBlock


def load_submission(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate submission key: ' + key)
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique)


def saved_submission_tool(store, submit):
    async def execute(ctx):
        value = load_submission(store.read(ctx.args['producer'], ctx.args['name'], ctx.args['revision']))
        submitted = submit(value)
        if inspect.isawaitable(submitted):
            await submitted
        return AgentToolResult([TextBlock('Saved submission validated and retained.')], terminate=True)
    return AgentTool('submit_work_product', 'Submit saved result',
        'Submit an exact saved JSON working-file revision through the same final owner validator. '
        'On rejection, patch the indicated fields and resubmit the new revision; do not rewrite the whole report.',
        {'type': 'object', 'properties': {'producer': {'type': 'string'}, 'name': {'type': 'string'},
            'revision': {'type': 'integer', 'minimum': 1}}, 'required': ['producer', 'name', 'revision'],
            'additionalProperties': False}, execute, requires_exclusive_batch=True)
