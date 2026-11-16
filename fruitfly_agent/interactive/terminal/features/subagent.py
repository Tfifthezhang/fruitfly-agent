"""Inspect child execution facts through a borrowed frontend capability."""
from collections import Counter
from typing import Callable

from fruitfly_agent.interactive.contracts.commands import (
    CommandPanel, CommandResult, CommandSection, InteractiveCommand,
)
from fruitfly_agent.interactive.contracts.subagents import SubagentMonitor
from fruitfly_agent.interactive.terminal.rendering.formatting import format_duration
from fruitfly_agent.interactive.terminal.rendering.panels import panel_result


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
            result_rows = [('Reference', value.result_reference or 'unavailable')]
            if value.error:
                result_rows.append(('Error', value.error))
            if value.summary:
                result_rows.append(('Summary', value.summary))
            if not value.error and not value.summary:
                result_rows.append(('Result', 'No result yet.'))
            return panel_result(CommandPanel('Subagent execution', (
                CommandSection('tools', 'Task', (
                    ('Task', value.task), ('Agent ID', value.agent_id), ('Run ID', value.run_id),
                    ('Model profile', value.model_profile or 'unknown'), ('Model', value.model or 'unknown'))),
                CommandSection('workflow', 'Status', (
                    ('State', value.state), ('Activity', value.activity), ('Cleanup', value.cleanup),
                    ('Recorded elapsed', 'unknown' if value.elapsed_seconds is None else format_duration(value.elapsed_seconds)))),
                CommandSection('environment', 'Recorded usage', (
                    ('Main model requests', str(value.model_requests)), ('Tool calls', str(value.tool_calls)),
                    ('Input tokens', known(value.input_tokens)), ('Output tokens', known(value.output_tokens)))),
                CommandSection('improvement', 'Result', tuple(result_rows)),
            ), 'Usage may be incomplete while execution is unfinished.'))
        snapshot = service.snapshot()
        executions = snapshot.executions
        rows = executions[-50:]
        counts = Counter(value.state for value in executions)
        sections = [
            CommandSection('environment', 'Counts', (
                ('Agents', str(len({value.agent_id for value in executions}))),
                ('Executions', str(len(executions))), ('Shown', str(len(rows))),
                ('Concurrency limit', str(snapshot.max_concurrent)), ('Revision', str(snapshot.revision)))),
            CommandSection('workflow', 'Statuses · all retained executions',
                tuple((state, str(count)) for state, count in counts.items()) or (('States', 'none'),)),
        ]
        if snapshot.poisoned:
            sections.append(CommandSection('improvement', 'Resource warning', (
                ('Admission', 'Resource retirement is unconfirmed; further execution is blocked.'),)))
        for index, value in enumerate(rows, 1):
            task = value.task[:160] + ('…' if len(value.task) > 160 else '')
            sections.append(CommandSection('tools', f'Task {index} · {value.state}', (
                ('Task', task), ('Agent ID', value.agent_id), ('Run ID', value.run_id),
                ('State', value.state), ('Activity', value.activity))))
        footer = '/subagent AGENT_ID [RUN_ID] for details.'
        if not executions:
            footer = 'No subagents. ' + footer
        if len(executions) > 50:
            footer = 'Counts cover all retained executions; showing the latest 50. Use exact IDs for earlier details. ' + footer
        return panel_result(CommandPanel('Subagents', tuple(sections), footer))
    return execute
