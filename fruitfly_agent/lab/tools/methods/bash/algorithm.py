"""Execute shell commands through the injected execution environment.

Commands use a configured finite default timeout. Bound the output body to the last 2000 lines and 51200
UTF-8 bytes. On truncation, attempt to save the full output and report whether
it was saved. Non-zero exits and backend aborts raise tool errors; user-signal cancellation propagates.
Throttle live stdout updates to about 100ms.
"""

from __future__ import annotations

from fruitfly_agent.runtime_spec.documents import parameter_default
import time
import asyncio
import math
from dataclasses import replace

from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.env import ExecOptions
from fruitfly_agent.core.observation import FailureInfo
from fruitfly_agent.core.tool_runtime import AgentTool, ToolCallContext
from fruitfly_agent.core.tool_runtime.authorization import ToolPermission
from fruitfly_agent.lab.tools.presentation import text_result
from fruitfly_agent.core.tool_runtime.presentation import ToolPresentation
from fruitfly_agent.lab.tools.truncate import DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES, truncate_tail

class CommandTimeoutError(RuntimeError):
    """Preserve the tool RuntimeError contract with structural timeout evidence."""
    def __init__(self, message):
        super().__init__(message)
        self.details = {'failure': FailureInfo('environment', 'environment.execute', 'timeout',
            'runtime_rule', effect_state='completed').to_dict()}


_BASH_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["run", "start", "poll", "cancel"], "description": "run waits; start returns a managed handle; poll/cancel use handle."},
        "handle": {"type": "string"},
        "wait_seconds": {"type": "number", "description": "Wait 0–30 seconds for a managed command; default 0.2."},
        "command": {"type": "string", "description": "Bash command to execute"},
        "description": {"type": "string", "description": "Optional short purpose of this command for the user. Do not include secrets."},
        "timeout": {
            "type": "number",
            "description": "Timeout in seconds; omission uses the configured finite default",
        },
    },
    "additionalProperties": False,
}

DEFAULT_TIMEOUT_SECONDS = parameter_default(__package__, 'defaults.yaml', 'settings.default_timeout_seconds')
_UPDATE_THROTTLE_SECONDS = 0.1


async def _execute(ctx: ToolCallContext) -> AgentToolResult:
    if ctx.env is None:
        raise RuntimeError("bash requires an ExecutionEnv")
    command = ctx.args["command"]
    timeout = ctx.args.get("timeout")

    if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0):
        raise RuntimeError("Invalid timeout: must be a positive number of seconds")

    last_update = 0.0

    async def on_chunk(text: str) -> None:
        nonlocal last_update
        if ctx.on_update is None:
            return
        now = time.monotonic()
        if now - last_update >= _UPDATE_THROTTLE_SECONDS:
            last_update = now
            await ctx.on_update(text)

    result = await ctx.env.exec(
        command,
        ExecOptions(cwd=ctx.env.cwd, timeout_seconds=timeout, on_stdout=on_chunk),
    )
    if not result.is_ok:
        raise RuntimeError(f"Failed to execute command: {result.error}")
    exec_result = result.unwrap()

    output = exec_result.stdout
    if exec_result.stderr:
        output = (output + "\n" if output else "") + exec_result.stderr

    truncation = truncate_tail(output)
    text = truncation.content
    details: dict = {}
    if truncation.truncated:
        full_path = ctx.env.create_temp_file(prefix="fruitfly-bash-", suffix=".log")
        if full_path.is_ok:
            saved = ctx.env.write_file(full_path.unwrap(), output)
            if saved.is_ok:
                details["full_output_path"] = full_path.unwrap()
                start_line = truncation.total_lines - truncation.output_lines + 1
                end_line = truncation.total_lines
                text += (
                    f"\n\n[Showing lines {start_line}-{end_line} of {truncation.total_lines}."
                    f" Full output: {details['full_output_path']}]"
                )
            else:
                text += "\n\n[Output truncated; full output could not be saved.]"
        else:
            text += "\n\n[Output truncated; full output could not be saved.]"

    if exec_result.termination_reason == 'timeout':
        raise CommandTimeoutError(_append_status(text, f'Command timed out after {timeout} seconds'))
    if exec_result.cancelled:
        if ctx.signal is not None and ctx.signal.is_set():
            raise asyncio.CancelledError
        raise RuntimeError(_append_status(text, "Command aborted"))

    if exec_result.exit_code not in (0, None):
        raise RuntimeError(_append_status(text, f"Command exited with code {exec_result.exit_code}"))

    return AgentToolResult(
        content=[TextBlock(text=text or "(no output)")],
        details=details,
    )


def _append_status(output: str, status: str) -> str:
    return f"{output}\n\n{status}" if output else status


def create_bash_tool(*, default_timeout_seconds=None, manager=None) -> AgentTool:
    if default_timeout_seconds is None:
        default_timeout_seconds = parameter_default(__package__, 'defaults.yaml', 'settings.default_timeout_seconds')
    if (isinstance(default_timeout_seconds, bool) or not isinstance(default_timeout_seconds, (int, float))
            or not math.isfinite(default_timeout_seconds) or default_timeout_seconds <= 0):
        raise ValueError('Bash requires a positive finite default timeout')
    async def execute(ctx):
        action = ctx.args.get('action', 'run')
        wait = ctx.args.get('wait_seconds', 0.2)
        if type(wait) not in (int, float) or not math.isfinite(wait) or not 0 <= wait <= 30:
            raise ValueError('wait_seconds must be finite and between 0 and 30')
        if action in {'poll', 'cancel'}:
            if manager is None:
                raise ValueError('managed commands require a runtime-owned command manager')
            handle = ctx.args.get('handle')
            return await (manager.poll(handle, wait_seconds=wait) if action == 'poll' else manager.cancel(handle))
        if action not in {'run', 'start'}:
            raise ValueError('unknown Bash action')
        if not isinstance(ctx.args.get('command'), str) or not ctx.args['command'].strip():
            raise ValueError('run/start requires a nonempty command')
        args = {**ctx.args, 'timeout': ctx.args.get('timeout', default_timeout_seconds)}
        if args['timeout'] is None:
            raise ValueError('timeout must be positive and finite')
        context = replace(ctx, args=args)
        if action == 'start':
            if manager is None:
                raise ValueError('managed commands require a runtime-owned command manager')
            return await manager.start_command(_execute, context, wait_seconds=wait)
        return await _execute(context)
    return AgentTool(
        permission=ToolPermission("execute", ()),
        name="bash",
        present_call=lambda args: ToolPresentation("execute",
            target=str(args.get("command", args.get("handle", "")))[:800]),
        present_result=lambda result: text_result("execute", result),
        label="Execute shell command",
        describe_call=lambda args: args.get("description", ""),
        description=(
            parameter_default(__package__, 'defaults.yaml', 'instructions.description')
        ),
        parameters=_BASH_SCHEMA,
        execute=execute,
    )
