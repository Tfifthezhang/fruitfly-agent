"""Sequential bounded evidence updates; successful prefixes survive later failures."""
import asyncio
from dataclasses import replace
import time

from fruitfly_agent.core.observation import FailureInfo, operation
from ...activity import report_activity
from ...identity import digest
from ...retry import retry_ready
from .prompts import update_prompt


async def maintain(snapshot, checkpoint, sources, config, auxiliary, estimate, policy):
    target = checkpoint.target_count if checkpoint.covered < checkpoint.target_count else len(sources)
    current = replace(checkpoint, target_count=target)
    deadline = time.monotonic() + config.update_timeout_seconds
    changed = False

    async def request(prompt, stage):
        await report_activity(snapshot, 'working-memory', stage)
        with operation('context.' + stage, origin='context', component_id='working-memory') as observed:
            result = await auxiliary.request_bounded(snapshot, system='Maintain bounded task memory.',
                prompt=prompt, max_tokens=config.auxiliary_max_tokens,
                timeout=config.auxiliary_timeout_seconds, deadline=deadline,
                attempts=config.auxiliary_attempts, input_limit=2**63-1, estimate=estimate)
            if result.outcome != 'succeeded':
                observed.fail(FailureInfo('context', stage, result.reason, 'runtime_rule'))
            await report_activity(snapshot, 'working-memory', stage, outcome=result.outcome,
                reason=result.reason, result=result)
            return result

    for _ in range(config.max_pages):
        if snapshot.signal is not None and snapshot.signal.is_set():
            raise asyncio.CancelledError
        if current.covered == target:
            break
        evidence = ''.join(sources[current.covered:target])[current.offset:]
        build = lambda page: update_prompt(config.update_instructions, current.memory, page, config.memory_tokens)
        size = auxiliary.page_size(evidence, system='Maintain bounded task memory.', build_prompt=build,
            max_chars=config.page_char_limit, max_tokens=config.auxiliary_max_tokens, estimate=estimate)
        fingerprint = digest({'policy': policy, 'memory': current.memory, 'page': evidence[:size]})
        if not retry_ready(current.attempt, fingerprint, time.time()):
            await report_activity(snapshot, 'working-memory', 'updating_memory', outcome='skipped', reason='retry_suppressed')
            break
        result = await request(build(evidence[:size]), 'updating_memory') if size > 0 else None
        text = result.text if result is not None and result.outcome == 'succeeded' else ''
        if text and estimate(text) > config.memory_tokens:
            result = await request(update_prompt(config.shrink_instructions, '', text, config.memory_tokens), 'shortening_memory')
            text = result.text if result.outcome == 'succeeded' else ''
        if not text or estimate(text) > config.memory_tokens:
            reason = 'input_capacity' if size <= 0 else 'memory_too_large' if text else result.reason if result is not None else 'input_capacity'
            await report_activity(snapshot, 'working-memory', 'updating_memory', outcome='failed', reason=reason)
            return replace(current, attempt={'fingerprint': fingerprint, 'timestamp': time.time()}), True
        covered, offset, left = current.covered, current.offset, size
        while covered < target and left >= len(sources[covered]) - offset:
            left -= len(sources[covered]) - offset
            covered, offset = covered + 1, 0
        current = replace(current, memory=text, covered=covered, offset=offset + left, attempt=None)
        changed = True
    return current, changed
