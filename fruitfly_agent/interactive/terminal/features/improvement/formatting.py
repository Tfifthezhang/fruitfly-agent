"""Render generic improvement activity for terminal observers."""
from fruitfly_agent.interactive.contracts.improvement import ImprovementActivity


def format_improvement_activity(activity: ImprovementActivity) -> str:
    """Show one batch's progress separately from request budget consumption."""
    text = activity.phase
    if activity.total > 0:
        filled = max(0, min(10, 10 * activity.completed // activity.total))
        text += f" [{'#' * filled}{'-' * (10 - filled)}] {activity.completed}/{activity.total}"
    if activity.model_calls:
        text += f" · model calls {activity.model_calls}"
    if activity.trial_calls:
        text += f" · trials used {activity.trial_calls}"
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
