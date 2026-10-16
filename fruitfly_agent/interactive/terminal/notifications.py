"""Observe optional improvement services and write terminal notices."""
from fruitfly_agent.interactive.terminal.features.improvement.formatting import format_improvement_activity
from fruitfly_agent.interactive.terminal.io.text import safe_terminal_text


class ImprovementNotifications:
    def __init__(self, *, progress, notice, acknowledge, busy, write):
        self.progress = progress
        self.notice = notice
        self.acknowledge = acknowledge
        self.busy = busy
        self.write = write
        self._last_notice = 0
        self._last_activity = None

    def show(self):
        progress = self.progress()
        if progress is not None:
            if progress.status == "running" and progress.activity is not None:
                identity = (progress.sequence, progress.activity)
                if identity != self._last_activity:
                    self._last_activity = identity
                    self.write("[improvement] " + safe_terminal_text(format_improvement_activity(progress.activity)) + "\n")
            elif progress.status not in {"idle", "running"} and progress.sequence != self._last_notice:
                self._last_notice = progress.sequence
                self.write(f"Improvement {progress.status}" +
                           (f": {safe_terminal_text(progress.error)}" if progress.error else "") + "\n")
        self.show_candidates()

    def show_candidates(self):
        if self.busy() or self.notice is None or self.acknowledge is None:
            return
        try:
            ids = self.notice()
            if ids:
                self.write(f"\n[{len(ids)} candidate(s) ready; not active. Use /improvement to review.]\n")
                self.acknowledge(ids)
        except (OSError, ValueError, RuntimeError) as exc:
            self.write(f"candidate notice unavailable: {exc}\n")
