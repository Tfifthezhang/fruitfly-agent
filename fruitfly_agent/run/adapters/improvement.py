"""Present search execution and progress through the improvement contract."""
from fruitfly_agent.interactive.contracts.improvement import ImprovementPreview, ImprovementActivity, ImprovementMethodView
from .candidates import candidate_view


class RunImprovementService:
    def __init__(self, *, jobs, activity, cancel, targets=lambda: (), methods=lambda role, target_id: ()):
        self.jobs = jobs
        self.activity = activity
        self.cancel = cancel
        self.experiment_routes = {}
        self.running_host = None
        self.targets = targets
        self.methods = methods

    def improvement_targets(self):
        return self.targets()

    def improvement_methods(self, role, target_id):
        return tuple(ImprovementMethodView(m.method_id, m.label, m.description, m.available,
            m.reason, m.default) for m in self.methods(role, target_id))

    def register_benchmark(self, host, selection, executor, direction="", *, remember=None, release=None):
        value = host.preview_selection(selection, executor, direction=direction)
        if len(self.experiment_routes) >= 16:
            _, _, expired_release = self.experiment_routes.pop(next(iter(self.experiment_routes)))
            if expired_release is not None:
                expired_release()
        self.experiment_routes[value.preview_token] = (host, remember, release)
        return ImprovementPreview(value.algorithm, value.label, value.cost_notice, value.details,
                                   value.target_id, value.preview_token, value.role)

    def improvement_preview(self, manifest, *, pack_id=None, direction="", **selection):
        value = self.jobs.improvement_preview(manifest, pack_id=pack_id, direction=direction, **selection)
        return ImprovementPreview(value.algorithm, value.label, value.cost_notice, value.details,
                                   value.target_id, value.preview_token, value.role)

    @property
    def running_improver(self):
        return self.running_host.running_improver if self.running_host is not None else None

    async def improve(self, manifest, direction, *, preview_token=""):
        host, remember, release = self.experiment_routes.pop(preview_token, (self.jobs, None, None))
        self.running_host = host
        try:
            if remember is not None:
                remember()
            return tuple(candidate_view(r) for r in await host.improve(manifest, direction, preview_token=preview_token))
        finally:
            self.running_host = None
            if release is not None:
                release()

    def improvement_activity(self):
        value = self.activity()
        if value is None:
            return None
        return ImprovementActivity(value.phase, value.completed, value.total,
            value.model_calls, value.model_limit, value.trial_calls, value.trial_limit, value.failed_trials,
            value.tokens.input_tokens, value.tokens.output_tokens, value.tokens.cache_read_tokens,
            value.tokens.cache_creation_tokens, value.tokens.reported_calls, value.tokens.missing_calls)

    def cancel_improvement(self):
        return self.cancel()

