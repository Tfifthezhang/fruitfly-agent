"""Recovery allowances count feedback rounds independently of batch width."""
import unittest
from fruitfly_agent.lab.agents.recovery import ToolRecoveryGuard
from fruitfly_agent.core.data_model import AssistantMessage, ToolResultMessage, TextBlock
from fruitfly_agent.core.errors import FatalError


class RecoveryTests(unittest.TestCase):
    def test_parallel_errors_allow_feedback_but_repeated_failed_rounds_stop(self):
        guard = ToolRecoveryGuard(2)
        assistant = AssistantMessage([], 'toolUse')
        errors = [ToolResultMessage(str(i), [TextBlock('invalid directory')], is_error=True) for i in range(5)]
        guard.check([assistant, *errors])
        guard.check([assistant, *errors])
        with self.assertRaises(FatalError):
            guard.check([assistant, *errors])

    def test_progress_and_changed_errors_reset_recovery(self):
        guard = ToolRecoveryGuard(1)
        assistant = AssistantMessage([], 'toolUse')
        error = ToolResultMessage('a', [TextBlock('invalid directory')], is_error=True)
        guard.check([assistant, error])
        guard.check([assistant, ToolResultMessage('b', [TextBlock('read succeeded')])])
        guard.check([assistant, error])
