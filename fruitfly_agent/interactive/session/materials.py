"""Project completed conversation tasks and record correction provenance."""
from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping

from fruitfly_agent.core.data_model import AssistantMessage, TextBlock, UserMessage
from fruitfly_agent.core.data_model import ContextItem
from fruitfly_agent.interactive.contracts.task_packs import CorrectionView, TaskPackService


def correction_snapshot(items: Iterable[ContextItem]) -> tuple[CorrectionView, ...]:
    rows: list[CorrectionView] = []
    current, output, tools = None, "", False

    def finish():
        if current is not None and output.strip():
            content = current.message.content
            text = content if isinstance(content, str) else "".join(
                block.text for block in content if isinstance(block, TextBlock)
            )
            rows.append(CorrectionView(current.id, text, output, tools or bool(rows)))

    for item in items:
        message = item.message
        if isinstance(message, UserMessage):
            finish()
            current, output, tools = item, "", False
        elif isinstance(message, AssistantMessage) and current is not None:
            tools = tools or bool(message.tool_calls)
            if message.stop_reason in {"stop", "length"}:
                output = message.text
    finish()
    return tuple(reversed(rows[-20:]))


class TaskMaterials:
    """Use injected public readers; the caller owns execution permission."""
    def __init__(self, *, service: Callable[[], TaskPackService],
                 items: Callable[[], Iterable[ContextItem]], session_path: Callable[[], str],
                 manifest: Callable[[], Mapping[str, object]]) -> None:
        self.service = service
        self.items = items
        self.session_path = session_path
        self.manifest = manifest

    def corrections(self) -> tuple[CorrectionView, ...]:
        return correction_snapshot(self.items())

    def save(self, task_id, pack_id, input, expected, **options):
        task = next((row for row in self.corrections() if row.task_id == task_id), None)
        if task is None:
            raise ValueError("completed task unavailable; select it again")
        source = {
            "session": self.session_path(), "message_id": task_id,
            "parent_manifest": str(self.manifest().get("digest", "")),
            "original_output_hash": "sha256:" + hashlib.sha256(task.output.encode()).hexdigest(),
        }
        return self.service().save_training_task(pack_id, input, expected, source=source, **options)
