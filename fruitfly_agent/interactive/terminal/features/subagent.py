"""Inspect child execution facts through a borrowed frontend capability."""
from typing import Callable
from fruitfly_agent.interactive.contracts.commands import CommandResult, InteractiveCommand
from fruitfly_agent.interactive.contracts.subagents import SubagentMonitor
from fruitfly_agent.interactive.terminal.io.text import safe_terminal_text


def subagent_handler(query: Callable[[], SubagentMonitor | None]) -> Callable[[InteractiveCommand], CommandResult]:
    def execute(command: InteractiveCommand) -> CommandResult:
        service = query()
        if service is None:
            return CommandResult(text='Subagent is disabled.\n')
        args = command.arguments
        if len(args) > 2:
            return CommandResult(text='usage: /subagent [AGENT_ID [RUN_ID]]\n')
        if args:
            try:
                value = service.detail(args[0], args[1] if len(args) == 2 else None)
            except ValueError:
                return CommandResult(text='Unknown subagent execution.\n')
            def known(number: object) -> str:
                return 'unknown' if number is None else str(number)
            text = (f'Subagent {value.agent_id} · {value.run_id}\n'
                f'State: {value.state} · Cleanup: {value.cleanup}\n'
                f'Task: {value.task}\nModel: {value.model_profile or "unknown"} · {value.model or "unknown"}\n'
                f'Activity: {value.activity}\nElapsed seconds: {known(value.elapsed_seconds)}\n'
                f'Main model requests: {value.model_requests} · Tool calls: {value.tool_calls}\n'
                f'Tokens: {known(value.input_tokens)} input · {known(value.output_tokens)} output\n'
                f'Result: {value.result_reference or "unavailable"}\n'
                f'{value.error or value.summary or "No result yet."}\n')
            return CommandResult(text=safe_terminal_text(text))
        snapshot = service.snapshot()
        if not snapshot.executions:
            return CommandResult(text='No subagents.\n')
        rows = snapshot.executions[-50:]
        text = f'Subagents · concurrency {snapshot.max_concurrent} · revision {snapshot.revision}\n'
        if snapshot.poisoned:
            text += 'Resource retirement is unconfirmed; further execution is blocked.\n'
        text += '\n'.join(f'{v.agent_id} · {v.run_id} · {v.state} · {v.task[:160]}' for v in rows) + '\n'
        if len(snapshot.executions) > 50:
            text += 'Showing the latest 50 executions. Use an exact ID for earlier details.\n'
        return CommandResult(text=safe_terminal_text(text))
    return execute
