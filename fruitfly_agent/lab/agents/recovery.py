"""Bound repeated tool failures by feedback opportunities, not batch width."""
from fruitfly_agent.core.data_model import AssistantMessage, ToolResultMessage
from fruitfly_agent.core.errors import FatalError


class ToolRecoveryGuard:
    def __init__(self, allowance):
        self.allowance = allowance
        self.previous = None
        self.failures = 0

    def check(self, messages):
        results = []
        for message in reversed(messages):
            if isinstance(message, AssistantMessage):
                break
            if isinstance(message, ToolResultMessage):
                results.append(message)
        if not results or any(not m.is_error for m in results):
            self.previous, self.failures = None, 0
            return
        signature = frozenset(m.text for m in results)
        self.failures = self.failures + 1 if signature == self.previous else 1
        self.previous = signature
        if self.failures > self.allowance:
            raise FatalError('repeated tool failures exhausted model feedback opportunities',
                details={'kind': 'tool_recovery_exhausted', 'feedback_opportunities': self.allowance})
