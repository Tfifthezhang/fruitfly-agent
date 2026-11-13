"""Presentation-only counters; event payloads retain exact values."""


def format_tokens(value: int) -> str:
    for divisor, unit in ((1_000_000, 'm'), (1_000, 'k')):
        if value >= divisor:
            scaled = round(value / divisor, 1)
            if unit == 'k' and scaled >= 1000:
                return '1m'
            return f'{scaled:g}{unit}'
    return str(value)


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f'{max(0., seconds):.1f}s'
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, rest = divmod(remainder, 60)
    return f'{hours}h {minutes}m {rest}s' if hours else f'{minutes}m {rest}s'
