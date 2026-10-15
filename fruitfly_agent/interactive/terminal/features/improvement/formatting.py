"""Render generic optimization activity for terminal observers."""
from fruitfly_agent.interactive.contracts.optimization import OptimizationActivity


def format_optimization_activity(activity: OptimizationActivity) -> str:
    """Show one batch's progress separately from request budget consumption."""
    text = activity.phase
    if activity.total > 0:
        filled = max(0, min(10, 10 * activity.completed // activity.total))
        text += f" [{'#' * filled}{'-' * (10 - filled)}] {activity.completed}/{activity.total}"
    if activity.model_limit:
        text += f" · model calls {activity.model_calls}/{activity.model_limit}"
    if activity.trial_limit:
        text += f" · trials used {activity.trial_calls}/{activity.trial_limit}"
    if activity.failed_trials:
        text += f" · failed trials {activity.failed_trials}"
    if activity.model_calls:
        if activity.usage_reported_calls:
            text += (f' · reported tokens {activity.input_tokens + activity.output_tokens:,}'
                     f' (in {activity.input_tokens:,} / out {activity.output_tokens:,};'
                     f' usage {activity.usage_reported_calls}/{activity.model_calls} calls)')
        else:
            text += ' · tokens unknown (Provider usage not yet reported)'
    return text
