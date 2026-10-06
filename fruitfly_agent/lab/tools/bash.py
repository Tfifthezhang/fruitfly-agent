"""Execute shell commands through the injected execution environment.

No default timeout. Bound the output body to the last 2000 lines and 51200
UTF-8 bytes. On truncation, attempt to save the full output and report whether
it was saved. Non-zero exits and process cancellation raise tool errors.
Throttle live stdout updates to about 100ms.
"""

from __future__ import annotations

import time

from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.env import ExecOptions
from fruitfly_agent.core.tool_runtime import AgentTool, ToolCallContext
from .truncate import DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES, truncate_tail

_BASH_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "Bash command to execute"},
        "timeout": {
            "type": "number",
            "description": "Timeout in seconds (optional, no default timeout)",
        },
    },
    "required": ["command"],
}

_UPDATE_THROTTLE_SECONDS = 0.1


async def _execute(ctx: ToolCallContext) -> AgentToolResult:
    if ctx.env is None:
        raise RuntimeError("bash requires an ExecutionEnv")
    command = ctx.args["command"]
    timeout = ctx.args.get("timeout")

    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
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
    if not exec_result.cancelled and timeout is not None and not output and exec_result.exit_code == -9:
        raise RuntimeError(_append_status(output, f"Command timed out after {timeout} seconds"))

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

    if exec_result.cancelled:
        raise RuntimeError(_append_status(text, "Command aborted"))

    if exec_result.exit_code not in (0, None):
        raise RuntimeError(_append_status(text, f"Command exited with code {exec_result.exit_code}"))

    return AgentToolResult(
        content=[TextBlock(text=text or "(no output)")],
        details=details,
    )


def _append_status(output: str, status: str) -> str:
    return f"{output}\n\n{status}" if output else status


def create_bash_tool() -> AgentTool:
    return AgentTool(
        name="bash",
        label="bash",
        description=(
            "Execute a bash command in the current working directory. Returns stdout "
            f"and stderr. Output is truncated to the last {DEFAULT_MAX_LINES} lines or "
            f"{DEFAULT_MAX_BYTES // 1024}KB (whichever is hit first). If truncated, the "
            "tool attempts to save the full output to a temp file and reports save failures. "
            "Optionally provide a timeout in seconds."
        ),
        parameters=_BASH_SCHEMA,
        execute=_execute,
    )
