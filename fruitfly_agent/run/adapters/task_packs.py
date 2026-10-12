"""Present task materials without depending on search or candidate services."""
from fruitfly_agent.interactive.contracts.task_packs import TaskPackView


class RunTaskPackService:
    def __init__(self, *, task_catalog, selected_target):
        self.task_catalog = task_catalog
        self.selected_target = selected_target

    def _task_target(self):
        return self.selected_target()

    def task_packs(self):
        return tuple(self._pack_view(s) for s in self.task_catalog().summaries(self._task_target()))

    @staticmethod
    def _pack_view(s):
        return TaskPackView(s.pack_id, s.name, s.source_hash, s.train_count,
                           s.validation_count, s.holdout_count, s.writable, s.error,
                           s.default_direction, s.acceptance_example)

    def save_training_task(self, pack_id, input, expected, **options):
        saved = self.task_catalog().save_training(pack_id, input, expected,
            target_id=self._task_target(), **options)
        return next(self._pack_view(s) for s in self.task_catalog().summaries(self._task_target()) if s.pack_id == saved)

    def task_pack_holdout(self, pack_id):
        return tuple((c.input, c.expected) for c in self.task_catalog().holdout(pack_id))
