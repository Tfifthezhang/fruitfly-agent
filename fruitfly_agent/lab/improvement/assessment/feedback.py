"""Declared development feedback projection; private assessment stays private."""
from dataclasses import replace


class FeedbackProjection:
    def __init__(self, metric_names=(), *, include_detail=False, all_metrics=False):
        self.metric_names = frozenset(metric_names)
        self.include_detail, self.all_metrics = include_detail, all_metrics

    def project(self, assessment):
        if assessment.visibility != 'development': return None
        return replace(assessment, metrics=tuple(m for m in assessment.metrics
            if self.all_metrics or m.name in self.metric_names), detail=assessment.detail if self.include_detail else '')
