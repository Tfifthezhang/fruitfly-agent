"""Budget-triggered compaction with no periodic auxiliary memory updates."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
import json
import re

from fruitfly_agent.core.data_model import ContextDecision, CustomMessage, ProviderView, CUSTOM_KIND_COMPACTION
from fruitfly_agent.core.data_model.context import ContextActivity
from fruitfly_agent.core.context.validation import valid_tool_links
from ....measurement.budget import MeasurementService, MeasurementConfig
from ....resources import SessionHistory, public_message
from .config import LayeredCompactionConfig
from .projection import shrink_results, split_history, anchors, summary_material
from .prompts import summary_prompt
from .state import digest, source_hash, validate_state, may_summarize


class LayeredCompactionReducer:
    mechanism_id = 'layered-compaction'
    estimate_source = 'heuristic_cjk'

    def __init__(self, config: LayeredCompactionConfig | None = None, *, history=None, summarizer=None):
        self.config = config or LayeredCompactionConfig()
        self.history = history or SessionHistory()
        self.summarizer = summarizer
        if self.config.mode == 'hybrid' and summarizer is None:
            raise ValueError('hybrid compaction requires an injected summary model')
        self.meter = MeasurementService(MeasurementConfig(margin_tokens=0, margin_ratio=0))
        self.policy = digest(asdict(self.config))

    def estimate(self, snapshot):
        return self.meter.estimate(ProviderView(snapshot.system_prompt, list(snapshot.messages),
            list(snapshot.tools), snapshot.model, snapshot.max_tokens))

    async def check_budget(self, snapshot):
        return await self._prepare(snapshot, force=False)

    async def react_to_overflow(self, snapshot, error):
        return await self._prepare(snapshot, force=True)

    async def _report(self, snapshot, stage, *, outcome='running', reason='', result=None):
        if snapshot.report_activity is not None:
            await snapshot.report_activity(ContextActivity(self.mechanism_id, stage, outcome,
                result.elapsed_seconds if result else 0., result.input_tokens if result else 0,
                result.output_tokens if result else 0, reason))

    async def _prepare(self, snapshot, *, force):
        if snapshot.signal is not None and snapshot.signal.is_set():
            raise asyncio.CancelledError
        items = snapshot.canonical_items
        self.history.bind(items)
        previous = validate_state(snapshot.context_state.get(self.mechanism_id), items, self.history)
        if (not items or not snapshot.rebase_allowed or not valid_tool_links(snapshot.messages)
                or not self.history.resource_prefix):
            return None
        measured = snapshot.measurement
        allowance = snapshot.context_window - (measured.output_reserve if measured else snapshot.max_tokens) - (measured.margin if measured else 0)
        if allowance <= 0:
            return None
        raw_before = self.estimate(snapshot)
        before = max(raw_before, measured.input_tokens or 0 if measured else 0)
        scale = max(1., before / max(1, raw_before))
        def size(messages):
            return self.estimate(replace(snapshot, messages=tuple(messages))) * scale
        target = allowance * self.config.target_ratio
        triggered = force or before >= allowance * self.config.trigger_ratio
        projected = shrink_results(snapshot.messages, items, self.history.resource_prefix, self.config)
        # A single oversized new result must also be externalized when the request cannot fit.
        if size(projected) > allowance:
            projected = shrink_results(projected, items, self.history.resource_prefix, self.config, force=True)
        changed = projected != snapshot.messages
        attempt = previous['attempt'] if previous and previous['policy'] == self.policy else None
        summary_text = ''
        summary_reference = ''
        representations = []
        if triggered and size(projected) > target:
            earlier, tail = split_history(projected, self.config,
                lambda message: self.meter.text_tokens(public_message(message)) + 8, target)
            if earlier:
                await self._report(snapshot, 'archiving_history')
                material = ''
                if self.config.mode == 'hybrid':
                    build = lambda text: summary_prompt(self.config.summary_instructions, text, self.config.summary_target_tokens)
                    material, representations, fits = summary_material(earlier, items,
                        self.history.resource_prefix, self.meter.text_tokens, build,
                        max(0, self.config.summary_input_max_tokens - 64))
                    fingerprint = digest({'policy': self.policy, 'material': material})
                    if fits and may_summarize(previous, self.policy, fingerprint, len(items)):
                        await self._report(snapshot, 'summarizing_history')
                        result = await self.summarizer.summarize(snapshot, self.config, material, self.meter.text_tokens)
                        attempt = {'fingerprint': fingerprint, 'source_count': len(items), 'outcome': result.outcome}
                        await self._report(snapshot, 'summarizing_history', outcome=result.outcome,
                            reason=result.reason, result=result)
                        if result.outcome == 'succeeded':
                            summary_text = result.text
                            summary_reference = self.history.put(summary_text)
                    else:
                        await self._report(snapshot, 'summarizing_history', outcome='skipped',
                            reason='retry_suppressed' if fits else 'input_capacity')
                ledger = self.history.put(json.dumps({'source_ids': [item.id for item in items],
                    'source_hash': source_hash(items), 'summary_input': representations,
                    'summary_artifact': summary_reference or None}, ensure_ascii=False, sort_keys=True))
                note = ('Earlier evidence is archived, not discarded.\n'
                    'Archive manifest: ' + self.history.resource_prefix + 'artifacts/' + ledger[7:]
                    + '\n[Context artifact ' + ledger + ']\n' + self.config.readback_instructions
                    + '\nHistory index: ' + self.history.resource_prefix + 'index')
                if summary_reference:
                    note += '\nSummary of supplied evidence:\n' + summary_text + '\n[Context artifact ' + summary_reference + ']'
                retained = anchors(items, tail)
                candidate = (*retained, CustomMessage(CUSTOM_KIND_COMPACTION, note), *tail)
                if size(candidate) < size(projected):
                    projected, changed = tuple(candidate), True
        if snapshot.signal is not None and snapshot.signal.is_set():
            raise asyncio.CancelledError
        if not changed or size(projected) >= before or size(projected) > allowance:
            if attempt != (previous['attempt'] if previous else None):
                state = self._state(items, snapshot.messages, attempt)
                return ContextDecision(state=state, mechanism_id=self.mechanism_id, base_revision=snapshot.revision)
            return None
        if not valid_tool_links(projected):
            return None
        await self._report(snapshot, 'reducing_context', outcome='succeeded')
        return ContextDecision(messages=tuple(projected), state=self._state(items, projected, attempt),
            retry=force, mechanism_id=self.mechanism_id, base_revision=snapshot.revision,
            estimated_tokens_before=before, metadata={'mode': self.config.mode, 'source_count': len(items),
                'estimated_tokens_after': int(size(projected))})

    def _state(self, items, messages, attempt):
        references = sorted({reference for message in messages if isinstance(message, CustomMessage)
            for reference in re.findall(r'\[Context artifact (sha256:[a-f0-9]{64})\]', message.text)})
        return {'policy': self.policy, 'source_count': len(items), 'source_hash': source_hash(items),
            'artifacts': references, 'attempt': attempt}

    def execution_artifacts(self):
        return self.history.execution_artifacts(prefix='layered_compaction', mechanism=self.mechanism_id)

    def validate_recovery(self, messages):
        self.history.validate_recovery(messages)
        if self.history.session is not None:
            validate_state(self.history.checkpoint(self.mechanism_id),
                tuple(self.history.session.context_items()), self.history)
