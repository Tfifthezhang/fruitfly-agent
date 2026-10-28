"""Incremental task memory with durable, code-owned evidence coverage."""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
from fruitfly_agent.core.data_model import ContextDecision, CustomMessage, UserMessage, CUSTOM_KIND_COMPACTION, ProviderView
from fruitfly_agent.core.context.validation import valid_tool_links
from fruitfly_agent.lab.algorithms import Algorithm, AlgorithmSpec
from ....history import SessionHistory, public_message
from ....measurement.budget import MeasurementService, MeasurementConfig
from ...inference import AuxiliaryText
from .config import WorkingMemoryConfig
from .prompts import update_prompt


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class WorkingMemoryReducer(Algorithm):
    spec = AlgorithmSpec('working-memory', 'working-memory-v1', 'session')
    estimate_source = 'heuristic_cjk'
    mechanism_id = 'working-memory'

    def __init__(self, config, provider, *, memory_model=None, memory_context_window=None,
                 memory_output_limit=None, history=None, meter=None):
        self.config = config
        self.history = history or SessionHistory()
        self.auxiliary = AuxiliaryText(provider, model=memory_model, context_window=memory_context_window,
            output_limit=memory_output_limit, meter=meter)
        self.meter = MeasurementService(MeasurementConfig(margin_tokens=0, margin_ratio=0))
        self.policy = digest(asdict(config))

    def estimate(self, snapshot):
        return self.meter.estimate(ProviderView(snapshot.system_prompt, list(snapshot.messages), list(snapshot.tools),
            snapshot.model, snapshot.max_tokens))

    def _sources(self, items):
        return ['[' + item.id + '] ' + public_message(item.message) + '\n' for item in items]

    def _load(self, state, items):
        if not state:
            return '', 0, 0
        required = {'policy', 'artifact', 'covered', 'offset', 'source_prefix'}
        if not isinstance(state, dict) or set(state) != required:
            raise ValueError('invalid working-memory checkpoint shape')
        # A changed candidate policy starts fresh and reprocesses canonical evidence.
        if state['policy'] != self.policy:
            return '', 0, 0
        covered, offset = state['covered'], state['offset']
        if (type(covered) is not int or not 0 <= covered <= len(items) or type(offset) is not int or offset < 0
                or covered == len(items) and offset != 0):
            raise ValueError('invalid working-memory coverage cursor')
        sources = self._sources(items)
        prefix = [(item.id, sources[i]) for i, item in enumerate(items[:covered + bool(offset)])]
        if state['source_prefix'] != digest(prefix) or offset and offset >= len(sources[covered]):
            raise ValueError('working-memory source coverage no longer matches canonical history')
        memory = self.history.text(state['artifact'])
        if self.meter.text_tokens(memory) > self.config.memory_tokens:
            raise ValueError('persisted working memory exceeds its policy bound')
        return memory, covered, offset

    async def check_budget(self, snapshot):
        return await self._prepare(snapshot, force=False)

    async def react_to_overflow(self, snapshot, error):
        return await self._prepare(snapshot, force=True)

    async def _prepare(self, snapshot, *, force):
        items = snapshot.canonical_items
        self.history.bind(items)
        if not items or not valid_tool_links(list(snapshot.messages)):
            return None
        previous = snapshot.context_state.get(self.mechanism_id)
        memory, covered, offset = self._load(previous, items)
        measured = snapshot.measurement
        allowance = snapshot.context_window - (measured.output_reserve if measured else snapshot.max_tokens) - (measured.margin if measured else 0)
        switch = force or max(self.estimate(snapshot), measured.input_tokens or 0 if measured else 0) >= allowance * self.config.switch_ratio
        if not switch and len(items) - covered < self.config.update_every_messages and not offset:
            return None
        sources = self._sources(items)
        updated = False
        for _ in range(self.config.max_pages):
            if covered == len(items):
                break
            evidence = ''.join(sources[covered:])[offset:]
            build = lambda page: update_prompt(self.config.update_instructions, memory, page, self.config.memory_tokens)
            size = self.auxiliary.page_size(evidence, system='Maintain bounded task memory.', build_prompt=build,
                max_chars=self.config.page_char_limit, max_tokens=self.config.auxiliary_max_tokens,
                estimate=self.meter.text_tokens)
            if size <= 0:
                return None
            result = await self.auxiliary.request(snapshot, system='Maintain bounded task memory.', prompt=build(evidence[:size]),
                max_tokens=self.config.auxiliary_max_tokens, timeout=self.config.auxiliary_timeout_seconds,
                attempts=self.config.auxiliary_attempts, estimate=self.meter.text_tokens)
            if result is None:
                return None
            if self.meter.text_tokens(result) > self.config.memory_tokens:
                result = await self.auxiliary.request(snapshot, system='Maintain bounded task memory.',
                    prompt=update_prompt(self.config.shrink_instructions, '', result, self.config.memory_tokens),
                    max_tokens=self.config.auxiliary_max_tokens, timeout=self.config.auxiliary_timeout_seconds,
                    attempts=self.config.auxiliary_attempts, estimate=self.meter.text_tokens)
                if result is None or self.meter.text_tokens(result) > self.config.memory_tokens:
                    return None
            memory, updated = result, True
            left = size
            while covered < len(sources) and left >= len(sources[covered]) - offset:
                left -= len(sources[covered]) - offset
                covered, offset = covered + 1, 0
            offset += left
        if not memory:
            return None
        reference = self.history.put(memory)
        state = {'policy': self.policy, 'artifact': reference, 'covered': covered, 'offset': offset,
            'source_prefix': digest([(item.id, sources[i]) for i, item in enumerate(items[:covered + bool(offset)])])}
        candidate = None
        # Unprocessed evidence never disappears, even when the update's page allowance is exhausted.
        if switch and snapshot.rebase_allowed and covered == len(items) and not offset:
            task = next((item.message for item in items if isinstance(item.message, UserMessage)), None)
            anchors = (task,) if task is not None else ()
            candidate = (CustomMessage(CUSTOM_KIND_COMPACTION, memory + '\n[Context artifact ' + reference + ']'), *anchors)
            after = self.estimate(replace(snapshot, messages=candidate))
            if after >= self.estimate(snapshot) or after > allowance:
                candidate = None
        if force and candidate is None:
            return None
        if candidate is None and not updated:
            return None
        return ContextDecision(messages=candidate, state=state, retry=force and candidate is not None,
            mechanism_id=self.mechanism_id, base_revision=snapshot.revision,
            estimated_tokens_before=self.estimate(snapshot), metadata={'covered': covered, 'offset': offset})

    def validate_recovery(self, messages):
        self.history.validate_recovery(messages)
        if self.history.session is not None:
            state = self.history.checkpoint(self.mechanism_id)
            self._load(state, tuple(self.history.session.context_items()))
