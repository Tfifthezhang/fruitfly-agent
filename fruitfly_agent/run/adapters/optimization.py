"""Present search execution and progress through the optimization contract."""
from fruitfly_agent.interactive.contracts.optimization import OptimizationPreview, OptimizationActivity
from .candidates import candidate_view


class RunOptimizationService:
    def __init__(self, *, jobs, activity, cancel):
        self.jobs = jobs
        self.activity = activity
        self.cancel = cancel

    def optimization_preview(self, manifest, *, pack_id=None, direction=""):
        value = self.jobs.optimization_preview(manifest, pack_id=pack_id, direction=direction)
        return OptimizationPreview(value.algorithm, value.label, value.cost_notice, value.details,
                                   value.target_id, value.preview_token)

    async def optimize(self, manifest, direction, *, preview_token=""):
        return tuple(candidate_view(r) for r in await self.jobs.optimize(manifest, direction, preview_token=preview_token))

    def optimization_activity(self):
        value = self.activity()
        if value is None:
            return None
        return OptimizationActivity(value.phase, value.completed, value.total,
            value.model_calls, value.model_limit, value.trial_calls, value.trial_limit, value.failed_trials,
            value.tokens.input_tokens, value.tokens.output_tokens, value.tokens.cache_read_tokens,
            value.tokens.cache_creation_tokens, value.tokens.reported_calls, value.tokens.missing_calls)

    def cancel_optimization(self):
        return self.cancel()

