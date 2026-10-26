"""Explicit startup review using the existing frontend's terminal ownership."""
import asyncio
import json
import sys
import threading
from fruitfly_agent.interactive.contracts.tool_services import ToolServiceStartPlan
from fruitfly_agent.interactive.terminal.io.text import safe_terminal_text
from fruitfly_agent.interactive.terminal.io.input import PollingLineEditor


async def approve_start(plan: ToolServiceStartPlan) -> bool:
    if not sys.stdin.isatty():
        return False
    review = f'\nStart external tool service {plan.name}?\nRuns on: {plan.location}\n' + json.dumps({
        'command': plan.command, 'args': list(plan.arguments), 'cwd': plan.working_directory,
        'environment variable names': list(plan.environment_names)}, ensure_ascii=False, indent=2)
    sys.stdout.write(safe_terminal_text(review) + '\nThis starts a process with current user permissions. Allow? [y/N] ')
    sys.stdout.flush()
    interrupted = threading.Event()
    editor = PollingLineEditor(sys.stdin, sys.stdout, interrupted)
    reader = asyncio.create_task(asyncio.to_thread(editor.read_line))
    try:
        answer = await asyncio.shield(reader)
        return answer is not None and answer.strip().lower() in {'y', 'yes'}
    finally:
        interrupted.set()
        if not reader.done():
            await asyncio.gather(reader, return_exceptions=True)
