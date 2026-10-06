"""Provider-backed summarizing compaction strategy.

The file separates research configuration, the summarization kernel,
FruitFlyAgent protocol adaptation, and assembly.  The kernel decides how to
represent history; only the adapter constructs Core ``ContextDecision`` values.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, replace
from typing import Callable

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import (
    AgentMessage,
    AssistantMessage, ImageBlock, TextBlock, ToolCallBlock, ToolResultMessage,
    CUSTOM_KIND_COMPACTION,
    ContextDecision,
    ContextSnapshot,
    CustomMessage,
    ProviderView,
    UserMessage,
)
from fruitfly_agent.core.extensions.protocols import Provider

from fruitfly_agent.lab.algorithms import Algorithm, AlgorithmSpec

from .config import SummarizingCompactorConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Algorithm configuration
# ---------------------------------------------------------------------------

_SUMMARIZE_SYSTEM = "You are a summarization model. Output only a continuity summary."
_SUMMARIZE_USER = (
    "The conversation history below is from an ongoing task. Write a compact "
    "continuity summary preserving: the original task and current goal, key "
    "decisions made, work completed, and exactly what remains unfinished with "
    "the next step. Under {word_limit} words. No new information.\n\n"
    "<history>\n{history}\n</history>"
)

_PROMPTS = {
    "continuity": (_SUMMARIZE_SYSTEM, _SUMMARIZE_USER),
}

# Private boundary value: algorithm kernel -> FruitFlyAgent adapter.
@dataclass(frozen=True)
class _SummarizingPlan:
    """Algorithm output before FruitFlyAgent decision adaptation."""

    messages: tuple[AgentMessage, ...]
    strategy: str
    cut: int
    dropped_estimated_tokens: int


class SummarizingCompactor(Algorithm):
    """Adapt one-shot summarization to Core's ``ContextReducer`` seam."""

    spec = AlgorithmSpec("summarizing", "summarizing-v2", "request")

    def __init__(
        self,
        config: SummarizingCompactorConfig,
        provider: Provider,
        *,
        summary_model: str | None = None,
        estimate_fn: Callable[[str], int] | None = None,
        summary_context_window: int | None = None,
        summary_output_limit: int | None = None,
    ) -> None:
        self.config = config
        self.provider = provider
        self.summary_model = summary_model
        if estimate_fn is None:
            from .estimate import resolve_token_estimator

            estimate_fn = resolve_token_estimator(config.token_estimator)
        self._estimate_fn = estimate_fn
        self.summary_context_window = summary_context_window
        self.summary_output_limit = summary_output_limit

    # ------------------------------------------------------------------
    # 2. FruitFlyAgent adapter: ContextSnapshot -> ContextDecision
    # ------------------------------------------------------------------

    def estimate(self, snapshot: ContextSnapshot) -> int:
        total = self.estimate_tokens(snapshot.system_prompt)
        total += sum(self._estimate_message(message) for message in snapshot.messages)
        for tool in snapshot.tools:
            total += self.estimate_tokens(
                tool.description + json.dumps(tool.parameters, ensure_ascii=False)
            )
        return total

    def _input_budget(self, snapshot: ContextSnapshot) -> int:
        # Reserve at least the actual main-model output allowance. Extra safety
        # margin scales down on small windows rather than consuming all input.
        reserve = max(snapshot.max_tokens, min(self.config.reserve_tokens, snapshot.context_window // 4))
        return max(0, snapshot.context_window - reserve)

    async def check_budget(self, snapshot: ContextSnapshot) -> ContextDecision | None:
        if not self.config.enabled or snapshot.overflow_attempt:
            return None
        budget = self._input_budget(snapshot)
        if budget <= 0 or self.estimate(snapshot) <= budget:
            return None
        plan = await self._plan_compaction(snapshot, self.config.keep_recent_tokens, strategy="budget")
        return self._decision(snapshot, plan) if plan else None

    async def react_to_overflow(self, snapshot: ContextSnapshot, error: Exception) -> ContextDecision | None:
        if not self.config.enabled or not 1 <= snapshot.overflow_attempt <= self.config.max_shrink_steps:
            return None
        keep = max(1, self.config.reactive_keep_recent_tokens // (2 ** (snapshot.overflow_attempt - 1)))
        plan = await self._plan_compaction(snapshot, keep, strategy="reactive")
        return self._decision(snapshot, plan) if plan else None

    def _decision(
        self,
        snapshot: ContextSnapshot,
        plan: _SummarizingPlan,
    ) -> ContextDecision:
        return ContextDecision(
            messages=plan.messages,
            retry=snapshot.trigger == "overflow",
            mechanism_id="summarizing",
            metadata={
                "strategy": plan.strategy,
                "cut": plan.cut,
                "droppedEstimatedTokens": plan.dropped_estimated_tokens,
            },
            estimated_tokens_before=self.estimate(snapshot),
        )

    # ------------------------------------------------------------------
    # 3. Algorithm kernel: cut, summary representation, fallback policy
    # ------------------------------------------------------------------

    def estimate_tokens(self, text: str) -> int:
        return max(0, self._estimate_fn(text))

    def _estimate_message(self, message: AgentMessage) -> int:
        from .estimate import estimate_message_tokens

        return estimate_message_tokens(message, self.estimate_tokens)

    async def _plan_compaction(self, snapshot: ContextSnapshot, keep_recent_tokens: int, *, strategy: str) -> _SummarizingPlan | None:
        from .cut import find_cut_point, valid_tool_links

        budget = self._input_budget(snapshot)
        if budget <= 0:
            return None
        messages = list(snapshot.messages)
        fixed = self._estimate_projection(snapshot, ())
        remaining = budget - fixed
        if remaining <= 0 or not valid_tool_links(messages):
            return None
        # Leave space for the summary, and progressively keep fewer whole turns.
        keep = min(keep_recent_tokens, max(1, remaining // 2))
        tried = set()
        for _ in range(self.config.max_shrink_steps):
            cut = find_cut_point(messages, keep, self._estimate_message)
            if cut is not None and cut not in tried:
                tried.add(cut)
                if valid_tool_links(messages[cut:]) and self._estimate_list(messages[cut:]) < remaining:
                    plan = await self._plan_at(snapshot, messages, cut, strategy=strategy)
                    if plan is not None:
                        return plan
                    # A failed summary must not fan out into more model calls.
                    return None
            if keep == 1:
                break
            keep = max(1, keep // 2)
        return None

    async def _plan_at(
        self,
        snapshot: ContextSnapshot,
        messages: list[AgentMessage],
        cut: int,
        *,
        strategy: str,
    ) -> _SummarizingPlan | None:
        history = messages[:cut]
        retained = messages[cut:]
        tokens_before = self._estimate_list(history)
        summary = await self._request_summary(
            snapshot, history
        )
        if summary is None:
            return None
        # Keep external artifact handles deterministically, without depending
        # on the model reproducing them. This appendix shares the input budget.
        refs = sorted(set(re.findall(r"(?:context://sha256/[a-f0-9]{64}|sha256:[a-f0-9]{64})", self._serialize_history(history, bounded=False))))
        if refs:
            summary += "\n[Retained external references]\n" + "\n".join(refs)
        summary_message = CustomMessage(kind=CUSTOM_KIND_COMPACTION, text=summary)
        candidate = tuple([summary_message, *retained])
        after = self._estimate_projection(snapshot, candidate)
        if after >= self.estimate(snapshot) or after > self._input_budget(snapshot):
            return None
        return _SummarizingPlan(
            messages=candidate,
            strategy=strategy,
            cut=cut,
            dropped_estimated_tokens=tokens_before,
        )

    def _estimate_projection(
        self, snapshot: ContextSnapshot, messages: tuple[AgentMessage, ...]
    ) -> int:
        return self.estimate(replace(snapshot, messages=messages))

    def _estimate_list(self, messages: list[AgentMessage]) -> int:
        return sum(self._estimate_message(message) for message in messages)

    def _build_summary_prompt(
        self,
        history: list[AgentMessage],
    ) -> tuple[str, str]:
        text = self._serialize_history(history)
        system_prompt, user_prompt = _PROMPTS[self.config.prompt_version]
        prompt = user_prompt.format(
            word_limit=self.config.summary_word_limit,
            history=self._bounded(text, self.config.history_char_limit),
        )
        return system_prompt, prompt

    # This is the runtime boundary: the prompt policy above is algorithmic,
    # while ProviderView construction and stream consumption adapt it to Core.
    async def _request_summary(
        self,
        snapshot: ContextSnapshot,
        history: list[AgentMessage],
    ) -> str | None:
        system_prompt, prompt = self._build_summary_prompt(history)
        output_limit = min(self.config.summary_max_tokens, self.summary_output_limit or self.config.summary_max_tokens)
        if self.summary_context_window is not None:
            budget = self.summary_context_window - output_limit
            if budget <= 0:
                return None
            # Account for message framing approximately; exact tokenizers may
            # be injected. Bound auxiliary history separately from main input.
            text = self._serialize_history(history)
            low, high = 0, min(len(text), self.config.history_char_limit)
            template = _PROMPTS[self.config.prompt_version][1]
            while low < high:
                middle = (low + high + 1) // 2
                candidate = template.format(word_limit=self.config.summary_word_limit, history=self._bounded(text, middle))
                if self.estimate_tokens(system_prompt + candidate) + 16 <= budget:
                    low = middle
                else:
                    high = middle - 1
            if low == 0:
                return None
            prompt = template.format(word_limit=self.config.summary_word_limit, history=self._bounded(text, low))
        view = ProviderView(
            system_prompt=system_prompt,
            messages=[UserMessage(content=prompt)],
            tools=[],
            model=self.summary_model or snapshot.model,
            max_tokens=output_limit,
        )
        for attempt in range(self.config.summary_attempts):
            if snapshot.signal is not None and snapshot.signal.is_set():
                return None
            try:
                async with asyncio.timeout(self.config.summary_timeout_seconds):
                    stream = self.provider(view, signal=snapshot.signal)
                    async for _ in stream:  # noqa: B007
                        pass
                    final = await stream.result()
                if final.stop_reason != "stop" or final.tool_calls:
                    return None
                return final.text.strip() or None
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "summarization attempt %d failed: %s: %s",
                    attempt + 1, type(exc).__name__, exc,
                )
        return None

    @staticmethod
    def _bounded(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        marker = "\n[content omitted]\n"
        if limit <= len(marker):
            return marker[:limit]
        head = (limit - len(marker)) // 2
        tail = limit - len(marker) - head
        return text[:head] + marker + text[-tail:]

    def _serialize_history(self, history: list[AgentMessage], *, bounded: bool = True) -> str:
        parts = []
        for message in history:
            if isinstance(message, CustomMessage):
                text = f"[{message.kind}]: {message.text}"
            else:
                content = message.content
                if isinstance(content, str):
                    body = content
                else:
                    blocks = []
                    for block in content:
                        if isinstance(block, TextBlock):
                            blocks.append(block.text)
                        elif isinstance(block, ToolCallBlock):
                            blocks.append(f"[tool call {block.id} {block.name}] " + json.dumps(block.input, ensure_ascii=False))
                        elif isinstance(block, ImageBlock):
                            blocks.append(f"[image {block.media_type}; image content unavailable to text summarizer]")
                        # Private model thinking is deliberately not summarized.
                    body = "\n".join(blocks)
                label = message.role
                if isinstance(message, ToolResultMessage):
                    label += f" {message.tool_call_id} error={message.is_error}"
                text = f"{label}: {body}"
            parts.append(self._bounded(text, self.config.per_message_char_limit) if bounded else text)
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# 4. Assembly
# ---------------------------------------------------------------------------


def install(
    config: AgentLoopConfig,
    provider: Provider,
    *,
    compaction: SummarizingCompactorConfig | None = None,
    summary_model: str | None = None,
) -> tuple[AgentLoopConfig, SummarizingCompactor]:
    return config, SummarizingCompactor(
        compaction or SummarizingCompactorConfig(),
        provider,
        summary_model=summary_model,
    )


__all__ = [
    "SummarizingCompactor",
    "SummarizingCompactorConfig",
    "install",
]
