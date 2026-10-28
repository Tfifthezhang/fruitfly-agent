"""Paged continuity summarization through Core's reduction contract."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import (ContextDecision, CustomMessage, UserMessage, CUSTOM_KIND_COMPACTION)
from fruitfly_agent.lab.algorithms import Algorithm, AlgorithmSpec
from ....history import SessionHistory, public_message
from ....measurement.methods.heuristic.estimator import estimate_message_tokens, resolve_token_estimator
from ...cut import find_cut_point, valid_tool_links
from ...inference import AuxiliaryText
from .config import SummarizingCompactorConfig
from .prompts import SYSTEM, prompt


@dataclass(frozen=True)
class _SummarizingPlan:
    messages: tuple
    strategy: str
    cut: int
    dropped_estimated_tokens: int


class SummarizingCompactor(Algorithm):
    spec = AlgorithmSpec('summarizing', 'summarizing-v3', 'request')

    def __init__(self, config, provider, *, summary_model=None, estimate_fn=None,
                 summary_context_window=None, summary_output_limit=None, history=None, meter=None):
        self.config, self.provider, self.summary_model = config, provider, summary_model
        self._custom_estimator = estimate_fn is not None
        self._estimate_fn = estimate_fn or resolve_token_estimator(config.token_estimator)
        self.summary_context_window, self.summary_output_limit = summary_context_window, summary_output_limit
        self.history = history or SessionHistory()
        self.auxiliary = AuxiliaryText(provider, model=summary_model, context_window=summary_context_window,
            output_limit=summary_output_limit, meter=meter)

    @property
    def estimate_source(self):
        return 'injected estimator' if self._custom_estimator else self.config.token_estimator

    def estimate_tokens(self, text):
        return max(0, self._estimate_fn(text))

    def _estimate_message(self, message):
        return estimate_message_tokens(message, self.estimate_tokens)

    def estimate(self, snapshot):
        total = self.estimate_tokens(snapshot.system_prompt) + 4
        total += sum(self._estimate_message(m) + 8 for m in snapshot.messages)
        total += sum(self.estimate_tokens(t.name + t.description + json.dumps(t.parameters, ensure_ascii=False)) + 12
                     for t in snapshot.tools if not t.hide_from_model)
        return total

    def _input_budget(self, snapshot):
        output = snapshot.measurement.output_reserve if snapshot.measurement is not None else snapshot.max_tokens
        margin = snapshot.measurement.margin if snapshot.measurement is not None else 0
        # Output and safety allowance are separate, never counted as alternatives.
        extra = min(self.config.reserve_tokens, snapshot.context_window // 4)
        return max(0, snapshot.context_window - output - margin - extra)

    async def check_budget(self, snapshot):
        if snapshot.signal is not None and snapshot.signal.is_set():
            return None
        if not self.config.enabled or snapshot.overflow_attempt:
            return None
        observed = snapshot.measurement.input_tokens if snapshot.measurement is not None else None
        if max(self.estimate(snapshot), observed or 0) <= self._input_budget(snapshot) * self.config.trigger_ratio:
            return None
        return await self._reduce(snapshot, self.config.keep_recent_tokens, 'budget')

    async def react_to_overflow(self, snapshot, error):
        if snapshot.signal is not None and snapshot.signal.is_set():
            return None
        if not self.config.enabled or not 1 <= snapshot.overflow_attempt <= self.config.max_shrink_steps:
            return None
        keep = max(1, self.config.reactive_keep_recent_tokens // (2 ** (snapshot.overflow_attempt - 1)))
        return await self._reduce(snapshot, keep, 'reactive')

    async def _reduce(self, snapshot, keep, strategy):
        if not snapshot.rebase_allowed or not valid_tool_links(list(snapshot.messages)):
            return None
        self.history.bind(snapshot.canonical_items)
        remaining = self._input_budget(snapshot) - self.estimate(replace(snapshot, messages=()))
        if remaining <= 0:
            return None
        messages = list(snapshot.messages)
        keep = min(keep, max(1, remaining // 2))
        tried = set()
        for _ in range(self.config.max_shrink_steps):
            cut = find_cut_point(messages, keep, self._estimate_message, allow_intra_turn=True)
            if cut is not None and cut not in tried:
                tried.add(cut)
                tail = messages[cut:]
                # When cutting inside an autonomous user turn, preserve its user instructions verbatim.
                if tail and not isinstance(tail[0], UserMessage):
                    task = next((m for m in messages if isinstance(m, UserMessage)), None)
                    if task is not None:
                        tail = [task, *tail]
                if self.estimate(replace(snapshot, messages=tuple(tail))) < self._input_budget(snapshot):
                    return await self._at(snapshot, messages, cut, tail, strategy)
            if keep == 1:
                break
            keep = max(1, keep // 2)
        return None

    async def _at(self, snapshot, messages, cut, tail, strategy):
        source = self._serialize_history(messages[:cut], bounded=False)
        # Admission precedes paid work; an unavailable archive cannot justify clearing evidence.
        reference = self.history.put(source)
        summary = await self._request_summary(snapshot, messages[:cut])
        if summary is None:
            return None
        refs = sorted(set(re.findall(r'(?:context://sha256/[a-f0-9]{64}|sha256:[a-f0-9]{64})', source)))
        summary += '\n[Context artifact ' + reference + ']'
        if refs:
            summary += '\n[Retained external references]\n' + '\n'.join(refs)
        candidate = (CustomMessage(CUSTOM_KIND_COMPACTION, summary), *tail)
        after = self.estimate(replace(snapshot, messages=candidate))
        if after >= self.estimate(snapshot) or after > self._input_budget(snapshot):
            return None
        return ContextDecision(messages=candidate, retry=snapshot.trigger == 'overflow', mechanism_id='summarizing',
            metadata={'strategy': strategy, 'cut': cut, 'source': reference,
                      'droppedEstimatedTokens': sum(self._estimate_message(m) for m in messages[:cut])},
            estimated_tokens_before=self.estimate(snapshot), base_revision=snapshot.revision)

    def _serialize_history(self, history, *, bounded=True):
        # Paging replaces lossy head/tail truncation. Both modes preserve every character.
        return '\n'.join(public_message(m) for m in history)

    async def _request_summary(self, snapshot, history):
        text = self._serialize_history(history, bounded=False)
        previous, offset = '', 0
        for _ in range(self.config.max_pages):
            build = lambda page: prompt(self.config.summary_instructions, previous, page, self.config.summary_word_limit)
            size = self.auxiliary.page_size(text[offset:], system=SYSTEM, build_prompt=build,
                max_chars=min(self.config.history_char_limit, self.config.per_message_char_limit),
                max_tokens=self.config.summary_max_tokens, estimate=self.estimate_tokens)
            if size <= 0:
                return None
            result = await self.auxiliary.request(snapshot, system=SYSTEM, prompt=build(text[offset:offset + size]),
                max_tokens=self.config.summary_max_tokens, timeout=self.config.summary_timeout_seconds,
                attempts=self.config.summary_attempts, estimate=self.estimate_tokens)
            if result is None:
                return None
            previous, offset = result, offset + size
            if offset == len(text):
                return previous
        # Do not clear history unless all pages were processed successfully.
        return None


def install(config: AgentLoopConfig, provider, *, compaction=None, summary_model=None):
    return config, SummarizingCompactor(compaction or SummarizingCompactorConfig(), provider, summary_model=summary_model)


__all__ = ['SummarizingCompactor', 'SummarizingCompactorConfig', 'install']
