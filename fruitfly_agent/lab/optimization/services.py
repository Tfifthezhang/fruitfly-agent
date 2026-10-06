"""Bounded native execution, append-only evidence, and shared root budgets."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
from inspect import isawaitable
import json
from pathlib import Path
from threading import Event
from uuid import uuid4

from fruitfly_agent.core.data_model import AssistantMessage, UserMessage, AgentToolResult, TextBlock
from fruitfly_agent.core.data_model.runtime import ProviderView
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.core.tool_runtime import AgentTool
from .search import Evaluation, TrialObservation, content_id
from .scoring import ScoreResult, task_policy
from .text_optimizer import SearchActivity
from .reporting import TokenUsage


class BudgetExhausted(RuntimeError):
    pass


class SearchBudget:
    """Reserve each harness Provider invocation and trial; internal retries are opaque."""
    def __init__(self, max_model_calls: int, max_trials: int):
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in (max_model_calls, max_trials)):
            raise ValueError("budgets must be positive")
        self.limits = {"model": max_model_calls, "trial": max_trials}
        self.used = {"model": 0, "trial": 0}
        self.exhausted_kind = ''

    def reserve(self, kind):
        if self.used[kind] >= self.limits[kind]:
            self.exhausted_kind = kind
            raise BudgetExhausted(f"{kind} call budget exhausted")
        self.used[kind] += 1


class SearchJournal:
    """Write intent before a paid call. Unknown requests are never auto-replayed."""
    def __init__(self, problem, path: Path | None = None):
        self.problem = problem
        self.path = path
        self.rows = []
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            # New search identities only; never append to an old interrupted job.
            with path.open("x", encoding="utf-8"):
                pass

    def append(self, kind, **fields):
        identity = {"schema": 1, "search_id": self.problem.search_id,
               "parent_manifest": self.problem.parent_manifest,
               "execution_id": self.problem.execution_id, "cases_digest": self.problem.cases_digest,
               "policy_id": self.problem.policy.policy_id}
        if any(key in fields and fields[key] != value for key, value in identity.items()):
            raise ValueError("search history identity mismatch")
        row = {**fields, **identity, "id": uuid4().hex, "kind": kind}
        encoded = json.dumps(row, ensure_ascii=False, allow_nan=False)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded + "\n")
                stream.flush()
        self.rows.append(json.loads(encoded))
        return row["id"]


def isolated_config(config, **changes):
    """Do not inherit interactive callbacks, tools, environment or Session."""
    return replace(config, session=None, env=None, hooks=None, tools=(),
                   max_context_recovery_attempts=1,
                   prepare_next_turn=None, get_steering_messages=None,
                   get_follow_up_messages=None, should_stop_after_turn=None,
                   before_tool_call=None, after_tool_call=None, on_partial=None, **changes)


class NativeSearchServices:
    capabilities = frozenset({"evaluate", "complete", "agent", "history"})

    def __init__(self, problem, config, target, *, budget, journal, stop=None,
                 timeout=30, max_tokens=1024, role_configs=None, scorer=None, evaluator=None):
        self.problem, self.config, self.target = problem, config, target
        self.budget, self.journal = budget, journal
        if journal.problem != problem:
            raise ValueError("journal belongs to a different optimization problem")
        self.stop = stop or Event()
        self.signal = asyncio.Event()
        self.timeout, self.max_tokens = timeout, max_tokens
        self.role_configs = dict(role_configs or {})
        self._budget_exhausted = False
        self.evaluator = evaluator
        self.scorer = scorer or task_policy(problem.policy.policy_id).score
        self._phase, self._completed, self._total, self._failed_trials = "Preparing", 0, 0, 0
        self._tokens = TokenUsage()

    def progress(self):
        return SearchActivity(self._phase, self._completed, self._total,
            self.budget.used["model"], self.budget.limits["model"],
            self.budget.used["trial"], self.budget.limits["trial"], self._failed_trials,
            replace(self._tokens, missing_calls=max(0, self.budget.used['model'] - self._tokens.reported_calls)))

    def check(self):
        if self.stop.is_set() or self.signal.is_set():
            raise asyncio.CancelledError("search cancelled")
        if self._budget_exhausted:
            raise BudgetExhausted("model call budget exhausted")

    def validate(self, text):
        self.target.validate(text)

    def record(self, kind, **fields):
        return self.journal.append(kind, **fields)

    def history(self):
        # Return detached values; strategies cannot mutate scored receipts.
        return tuple(json.loads(json.dumps(row)) for row in self.journal.rows)

    def _config(self, role):
        return self.role_configs.get(role, self.config)

    def _provider(self, config, role, **context):
        def provider(view, *, signal=None):
            self.check()
            try:
                self.budget.reserve("model")
            except BudgetExhausted:
                self._budget_exhausted = True
                raise
            attempt = self.record("request", role=role, model=view.model,
                                  max_tokens=view.max_tokens, status="pending", **context)
            async def events():
                try:
                    message = await config.provider(view, signal=self.signal).result()
                    usage = asdict(message.usage) if message.usage is not None and any(asdict(message.usage).values()) else None
                    if usage is not None:
                        self._tokens = TokenUsage(**{name: getattr(self._tokens, name) + usage.get(name, 0)
                            for name in ('input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_creation_tokens')},
                            reported_calls=self._tokens.reported_calls + 1)
                    self.record("response", attempt_id=attempt, role=role,
                                status="ok", usage=usage)
                    yield StreamDone(message)
                except asyncio.CancelledError:
                    self.record("response", attempt_id=attempt, role=role,
                                status="cancelled", usage=None)
                    raise
                except Exception as exc:
                    self.record("response", attempt_id=attempt, role=role,
                                status="error", error=type(exc).__name__, usage=None)
                    raise
            return AssistantMessageEventStream(events())
        return provider

    async def evaluate(self, text, partition, *, cases=None):
        self.check()
        if text != self.problem.baseline.text:
            self.validate(text)
        if partition not in ("train", "validation"):
            raise ValueError("unknown evaluation partition")
        allowed = getattr(self.problem, partition)
        selected = tuple(cases) if cases is not None else allowed
        if not selected or any(case not in allowed for case in selected):
            raise ValueError("case is outside the frozen partition")
        self._phase = "Evaluating training" if partition == "train" else "Evaluating selection validation"
        self._completed, self._total = 0, len(selected)
        observations = []
        for case in selected:
            self.check()
            self.budget.reserve("trial")
            evaluation_id = self.record("trial-start", candidate_id=content_id(text),
                                        case_id=case.case_id, partition=partition, text=text)
            output, score, feedback, status = "", None, "", "ok"
            try:
                output, score, feedback = await self._trial(text, case, evaluation_id)
                self.problem.policy.utility(score)
            except BudgetExhausted:
                self.record("trial-stop", evaluation_id=evaluation_id, status="budget_exhausted")
                raise
            except asyncio.CancelledError:
                self.record("trial-stop", evaluation_id=evaluation_id, status="cancelled")
                raise
            except Exception as exc:
                status, score, feedback = "error", None, type(exc).__name__
            observation = TrialObservation(evaluation_id, content_id(text), case.case_id, partition,
                                           self.problem.execution_id, self.problem.policy.policy_id,
                                           status, score, output[:4000], feedback[:1000])
            observations.append(observation)
            self._completed += 1
            self._failed_trials += int(status == "error")
            self.record("trial", **asdict(observation))
        score = (sum(o.score for o in observations) / len(observations)
                 if all(o.status == "ok" for o in observations) else None)
        self.record("evaluation", candidate_id=content_id(text), text=text, partition=partition,
                    score=score, observation_ids=[o.evaluation_id for o in observations])
        return Evaluation(text, tuple(observations), score)

    async def _trial(self, text, case, evaluation_id):
        if self.evaluator is not None:
            score = self.evaluator(text, case)
            if isawaitable(score):
                score = await asyncio.wait_for(score, self.timeout)
            if isinstance(score, bool):
                raise ValueError("metric must be a finite number, not boolean")
            return "", float(score), "scored by " + self.problem.policy.policy_id
        config = self.target.prepare_trial(self.config, text)
        provider = self._provider(config, "trial", evaluation_id=evaluation_id,
                                  candidate_id=content_id(text), case_id=case.case_id)
        config = isolated_config(config, provider=provider,
                                 max_tokens=min(config.max_tokens, self.max_tokens), max_turns=1, max_tool_calls_per_turn=0)
        result = await asyncio.wait_for(run_agent_loop(config, [UserMessage(content=case.input)],
                                        signal=self.signal), self.timeout)
        if self._budget_exhausted:
            raise BudgetExhausted("model call budget exhausted")
        if result.is_error:
            raise RuntimeError("trial loop failed")
        answers = [m for m in result.messages if isinstance(m, AssistantMessage)]
        if not answers or answers[-1].stop_reason != "stop" or answers[-1].tool_calls:
            raise ValueError("trial returned incomplete or non-text output")
        output = "".join(m.text for m in result.messages if isinstance(m, AssistantMessage)).strip()
        scored = self.scorer(output, case)
        if isawaitable(scored):
            scored = await asyncio.wait_for(scored, self.timeout)
        if isinstance(scored, ScoreResult):
            return output, scored.score, scored.feedback
        if isinstance(scored, bool):
            raise ValueError("metric must be a finite number, not boolean")
        return output, float(scored), "scored by " + self.problem.policy.policy_id

    async def complete(self, role, system, prompt):
        self.check()
        if len(prompt) > 60000:
            raise ValueError("generation input exceeds 60000 characters")
        self._phase, self._completed, self._total = f"Generating ({role})", 0, 0
        config = self._config(role)
        generation_id = uuid4().hex
        message = await asyncio.wait_for(self._provider(config, role, generation_id=generation_id)(ProviderView(
            system_prompt=system, messages=[UserMessage(content=prompt)], tools=[],
            model=config.model, max_tokens=min(self.max_tokens, config.max_tokens))).result(), self.timeout)
        if message.stop_reason != "stop" or not message.text.strip() or message.tool_calls:
            raise ValueError("generation requires complete, nonempty text without tool calls")
        self.record("generation", generation_id=generation_id, role=role, text=message.text)
        return message.text

    async def agent(self, role, system, prompt, *, files, output_path):
        """Core tool agent over a private, bounded text workspace. No shell/filesystem access."""
        self.check()
        if len(prompt) > 60000:
            raise ValueError("agent input exceeds 60000 characters")
        self._phase, self._completed, self._total = f"Tool agent ({role})", 0, 0
        workspace = dict(files)
        if sum(len(text) for text in workspace.values()) > 120000:
            raise ValueError("research workspace exceeds its text limit")
        agent_id = uuid4().hex
        consumed = set()
        if output_path in workspace:
            raise ValueError("output must be a new file")
        read_paths = frozenset(workspace)
        written = False
        tool_executions = 0
        def reserve_tool():
            nonlocal tool_executions
            self.check()
            if tool_executions >= 8:
                raise BudgetExhausted("research tool execution budget exhausted")
            tool_executions += 1
        async def read(ctx):
            reserve_tool()
            path = ctx.args["path"]
            if path not in read_paths:
                raise ValueError("read path is not authorized")
            consumed.add(path)
            self.record("agent-read", agent_id=agent_id, role=role, path=path, content_id=content_id(workspace[path]))
            return AgentToolResult(content=[TextBlock(text=workspace[path])])
        async def write(ctx):
            nonlocal written
            reserve_tool()
            if not read_paths <= consumed:
                raise ValueError("read the authorized inputs before writing the output")
            path, text = ctx.args["path"], ctx.args["content"]
            if path != output_path or not isinstance(text, str) or not 1 <= len(text.strip()) <= 30000:
                raise ValueError("write requires the declared output path and bounded text")
            workspace[path], written = text, True
            self.record("agent-write", agent_id=agent_id, role=role, path=path, content_id=content_id(text), text=text)
            return AgentToolResult(content=[TextBlock(text="Saved " + path)])
        schema = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
        tools = (AgentTool(name="read", label="read", description="Read an authorized research text file.",
                           parameters=schema, execute=read),
                 AgentTool(name="write", label="write", description="Write the declared text output file.",
                           parameters={"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                                       "required": ["path", "content"]}, execute=write))
        config = self._config(role)
        # Tools are capabilities over detached memory, with no ExecutionEnv or active Session.
        layout = "\nAuthorized input files: " + json.dumps(sorted(read_paths)) + "\nDeclared output file: " + output_path
        config = replace(isolated_config(config, provider=self._provider(config, role, agent_id=agent_id), system_prompt=system + layout,
                                         max_turns=4, max_tool_calls_per_turn=8, max_tokens=min(self.max_tokens, config.max_tokens)), tools=tools)
        result = await asyncio.wait_for(run_agent_loop(config, [UserMessage(content=prompt)], signal=self.signal), self.timeout)
        if self._budget_exhausted:
            raise BudgetExhausted("model call budget exhausted")
        if result.is_error or not written:
            raise ValueError("engineering agent did not produce its declared file")
        if not read_paths <= consumed:
            raise ValueError("engineering agent must read its authorized inputs, including the Skill")
        answers = [m for m in result.messages if isinstance(m, AssistantMessage)]
        if not answers or answers[-1].stop_reason != "stop":
            raise ValueError("engineering agent did not finish normally")
        self.record("agent-result", agent_id=agent_id, role=role, output_id=content_id(workspace[output_path]),
                    consumed=sorted(consumed))
        return workspace[output_path]
