"""A single bounded structured-summary operation, with explicit rejection reasons."""
from dataclasses import replace
from ...inference import AuxiliaryText
from .prompts import SECTIONS, summary_prompt


class HistorySummarizer:
    def __init__(self, provider, *, model, context_window, output_limit, meter=None):
        self.auxiliary = AuxiliaryText(provider, model=model, context_window=context_window,
            output_limit=output_limit, meter=meter)

    async def summarize(self, snapshot, config, material, estimate):
        result = await self.auxiliary.request_once(snapshot, system='Summarize archived task evidence.',
            prompt=summary_prompt(config.summary_instructions, material, config.summary_target_tokens),
            max_tokens=config.summary_max_output_tokens, timeout=config.summary_timeout_seconds,
            input_limit=config.summary_input_max_tokens, estimate=estimate)
        if result.outcome != 'succeeded':
            return result
        headings = ['## ' + name for name in SECTIONS]
        positions = [result.text.find(heading) for heading in headings]
        reason = ('summary_too_large' if estimate(result.text) > config.summary_target_tokens else
                  'invalid_structure' if any(result.text.count(h) != 1 for h in headings)
                  or positions != sorted(positions) else '')
        return replace(result, text='', outcome='failed', reason=reason) if reason else result
