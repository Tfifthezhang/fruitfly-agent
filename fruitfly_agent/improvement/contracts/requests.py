"""Pure experiment submission values, independent of frontends and hosts."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class WorkflowRequest:
    instruction: str = ''
    input_paths: tuple[str, ...] = ()
    component_ids: tuple[str, ...] = ()
    generator_id: str = 'agent-editor-v1'
    scope: str = 'task'
    rounds: int = 1
    timeouts: dict[str, float] = field(default_factory=lambda: {'editor_seconds':1200,'execution_seconds':3600,'evaluator_seconds':1200})
    direction: str = ''
    task_pack_id: str = ''
    execution_id: str = 'agent-task'
    execution_parameters: tuple[tuple[str, object], ...] = ()
    retain_experience: bool = False

