"""Pure retry admission shared by reduction owners; never alters coverage."""

RETRY_COOLDOWN_SECONDS = 60.


def retry_ready(attempt, fingerprint, now):
    return (attempt is None or attempt['fingerprint'] != fingerprint
        or now - attempt['timestamp'] >= RETRY_COOLDOWN_SECONDS)


def may_summarize(previous, policy, fingerprint, source_count):
    if previous is None or previous['policy'] != policy or previous['attempt'] is None:
        return True
    attempt = previous['attempt']
    return attempt['fingerprint'] != fingerprint and source_count - attempt['source_count'] >= 8
