"""Public single-version Eval operations for independent consumers."""
from .contracts import EvaluationRequest
from .execution import execute_request as run_evaluation
from .service import prepare_evaluation, check_evaluation, read_report, stop_evaluation
from .task_selection import list_prepared_tasks, select_prepared_tasks

__all__ = ['EvaluationRequest', 'run_evaluation', 'prepare_evaluation', 'check_evaluation', 'read_report', 'stop_evaluation',
           'list_prepared_tasks', 'select_prepared_tasks']
