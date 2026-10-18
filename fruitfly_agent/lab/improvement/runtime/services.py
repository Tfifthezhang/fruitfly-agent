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
from fruitfly_agent.lab.improvement.contracts.search import Evaluation, TrialObservation, content_id
from fruitfly_agent.lab.improvement.tasks.scoring import ScoreResult, task_policy
from fruitfly_agent.lab.improvement.api import SearchActivity
from fruitfly_agent.lab.improvement.runtime.reporting import TokenUsage
from fruitfly_agent.lab.improvement.trials import BatchEvaluation, BatchObservation, TrialOutcome


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
    capabilities = frozenset({"evaluate", "complete", "agent", "history", "workflow-trials", "target-trials"})

    def __init__(self, problem, config, target, *, budget, journal, stop=None,
                 timeout=30, max_tokens=1024, role_configs=None, scorer=None, evaluator=None,
                 trial_executor=None, trial_targets=()):
        self.problem, self.config, self.target = problem, config, target
        self.budget, self.journal = budget, journal
        if journal.problem != problem:
            raise ValueError("journal belongs to a different improvement problem")
        self.stop = stop or Event()
        self.signal = asyncio.Event()
        self.timeout, self.max_tokens = timeout, max_tokens
        self.role_configs = dict(role_configs or {})
        self._budget_exhausted = False
        self.evaluator = evaluator
        self.trial_executor = trial_executor
        self.trial_targets = tuple(trial_targets)
        self.scorer = scorer or task_policy(problem.policy.policy_id).score
        self._accounting = {"tokens": TokenUsage(), "failures": 0}
        self._phase, self._completed, self._total, self._failed_trials = "Preparing", 0, 0, 0
        self._tokens = TokenUsage()

    @property
    def _tokens(self):
        return self._accounting['tokens']

    @_tokens.setter
    def _tokens(self, value):
        self._accounting['tokens'] = value

    @property
    def _failed_trials(self):
        return self._accounting['failures']

    @_failed_trials.setter
    def _failed_trials(self, value):
        self._accounting['failures'] = value

    def for_target(self, problem, target):
        """Borrow one root budget, cancellation signal, usage ledger and journal."""
        root = self
        class ScopedJournal:
            def __init__(self):
                self.problem, self.rows = problem, root.journal.rows
            def append(self, kind, **fields):
                return root.journal.append(kind, **fields)
        child = NativeSearchServices(problem, self.config, target, budget=self.budget,
            journal=ScopedJournal(), stop=self.stop, timeout=self.timeout, max_tokens=self.max_tokens,
            role_configs=self.role_configs, scorer=self.scorer, evaluator=self.evaluator,
            trial_executor=self.trial_executor)
        child.trial_targets = self.trial_targets
        child.signal, child._accounting = self.signal, self._accounting
        return child

    def progress(self):
        return SearchActivity(self._phase, self._completed, self._total,
            self.budget.used["model"], self.budget.limits["model"],
            self.budget.used["trial"], self.budget.limits["trial"], self._failed_trials,
            replace(self._tokens, missing_calls=max(0, self.budget.used['model'] - self._tokens.reported_calls)))

    def check(self):
        self.check_cancellation()
        if self._budget_exhausted:
            raise BudgetExhausted("model call budget exhausted")

    def check_cancellation(self):
        if self.stop.is_set() or self.signal.is_set():
            raise asyncio.CancelledError("search cancelled")

    def set_phase(self, phase):
        self._phase, self._completed, self._total = phase, 0, 0

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
            self.record("trial-output", evaluation_id=evaluation_id, output=output,
                        output_hash=content_id(output))
        score = (sum(o.score for o in observations) / len(observations)
                 if all(o.status == "ok" for o in observations) else None)
        self.record("evaluation", candidate_id=content_id(text), text=text, partition=partition,
                    score=score, observation_ids=[o.evaluation_id for o in observations])
        return Evaluation(text, tuple(observations), score)

    async def _trial(self, text, case, evaluation_id):
        return await self.execute_case(text, case, evaluation_id)

    async def execute_case(self, text, case, evaluation_id, *, external=True, scorer=None, policy_id=None):
        if self.evaluator is not None:
            score = self.evaluator(text, case)
            if isawaitable(score):
                score = await asyncio.wait_for(score, self.timeout)
            if isinstance(score, bool):
                raise ValueError("metric must be a finite number, not boolean")
            return "", float(score), "scored by " + self.problem.policy.policy_id
        config = self.target.prepare_trial(self.config, text)
        selected_id = self.target.snapshot().target_id
        execution_target = self.target if callable(getattr(self.target, 'prepare_execution', None)) else None
        for target in self.trial_targets:
            if target.snapshot().target_id != selected_id:
                if callable(getattr(target, 'prepare_execution', None)):
                    if execution_target is not None:
                        raise ValueError('multiple trial execution controllers')
                    execution_target = target
        execution_text = text if execution_target is self.target else execution_target.snapshot().text if execution_target else ''
        if execution_target is not None:
            config = execution_target.prepare_trial(config, execution_text)
        # Substitute the candidate in its registered projection position rather
        # than appending it after all fixed documents.
        for target in self.trial_targets:
            if target is not execution_target:
                candidate_text = text if target.snapshot().target_id == selected_id else target.snapshot().text
                config = target.prepare_trial(config, candidate_text)
        provider = self._provider(config, "trial", evaluation_id=evaluation_id,
                                  candidate_id=content_id(text), case_id=case.case_id)
        def prepare_execution(config):
            prepared = execution_target.prepare_execution(config, execution_text)
            if (prepared.provider is not provider or prepared.model != config.model
                    or prepared.session is not None or prepared.env is not None or prepared.tools):
                raise ValueError('target execution must retain budgeted model and isolated trial boundaries')
            return prepared
        if external and self.trial_executor is not None:
            # The executor constructs task-owned tools/environment; never borrow
            # the production Session, environment, callbacks or tool objects.
            config = isolated_config(config, provider=provider,
                                     max_tokens=min(config.max_tokens, self.max_tokens))
            if execution_target is not None:
                config = prepare_execution(config)
            try:
                outcome = await asyncio.wait_for(
                    self.trial_executor.run(config, case, signal=self.signal), self.timeout)
            except Exception:
                if self._budget_exhausted:
                    raise BudgetExhausted("model call budget exhausted") from None
                raise
            if not isinstance(outcome, TrialOutcome):
                raise ValueError("external trial executor must return TrialOutcome")
            if self._budget_exhausted:
                raise BudgetExhausted("model call budget exhausted")
            return outcome.output, outcome.score, outcome.feedback
        config = isolated_config(config, provider=provider,
                                 max_tokens=min(config.max_tokens, self.max_tokens), max_turns=1, max_tool_calls_per_turn=0)
        if execution_target is not None:
            config = prepare_execution(config)
        result = await asyncio.wait_for(run_agent_loop(config, [UserMessage(content=case.input)],
                                        signal=self.signal), self.timeout)
        if self._budget_exhausted:
            raise BudgetExhausted("model call budget exhausted")
        if result.is_error:
            raise RuntimeError("trial loop failed")
        answers = [m for m in result.messages if isinstance(m, AssistantMessage)]
        if not answers or answers[-1].stop_reason != "stop" or answers[-1].tool_calls:
            raise ValueError("trial returned incomplete or non-text output")
        output = (answers[-1].text if execution_target is not None else
                  "".join(m.text for m in result.messages if isinstance(m, AssistantMessage))).strip()
        scored = (scorer or self.scorer)(output, case)
        if isawaitable(scored):
            scored = await asyncio.wait_for(scored, self.timeout)
        if isinstance(scored, ScoreResult):
            return output, scored.score, scored.feedback
        if isinstance(scored, bool):
            raise ValueError("metric must be a finite number, not boolean")
        return output, float(scored), "scored by " + (policy_id or self.problem.policy.policy_id)

    async def run_cases(self, text, cases, *, stage, repeats=1, policy=None):
        """Learning and confirmation have separate receipts from original selection.

        The workflow owns the frozen case authorization. Strategies only receive
        its restricted search view, never this confirmation capability.
        """
        self.check()
        if stage not in {"learning", "confirmation"}:
            raise ValueError("invalid workflow trial stage")
        if type(repeats) is not int or not 1 <= repeats <= 5:
            raise ValueError("workflow trial repeats must be 1–5")
        cases = tuple(cases)
        if not 1 <= len(cases) <= 12 or len({c.case_id for c in cases}) != len(cases):
            raise ValueError("workflow trial batch requires 1–12 distinct tasks")
        if text != self.problem.baseline.text:
            self.validate(text)
        self._phase = "Evaluating learning exercises" if stage == "learning" else "Independent confirmation"
        self._completed, self._total = 0, len(cases) * repeats
        observations = []
        for repeat in range(repeats):
            for case in cases:
                self.check()
                self.budget.reserve("trial")
                evaluation_id = self.record("batch-trial-start", candidate_id=content_id(text),
                    case_id=case.case_id, stage=stage, repeat=repeat,
                    task_policy_id=policy.policy_id if policy is not None else self.problem.policy.policy_id,
                    task_execution_id=policy.execution_id if policy is not None else self.problem.execution_id)
                output, score, feedback, status = "", None, "", "ok"
                try:
                    output, score, feedback = await self.execute_case(
                        text, case, evaluation_id, external=stage == "confirmation",
                        scorer=policy.score if policy is not None else None,
                        policy_id=policy.policy_id if policy is not None else None)
                    self.problem.policy.utility(score)
                except (BudgetExhausted, asyncio.CancelledError):
                    self.record("batch-trial-stop", evaluation_id=evaluation_id, stage=stage,
                                status="interrupted")
                    raise
                except Exception as exc:
                    status, score, feedback = "error", None, type(exc).__name__
                observation = BatchObservation(evaluation_id, content_id(text), case.case_id,
                    stage, repeat, status, score, output[:4000], feedback[:1000])
                observations.append(observation)
                self.record("batch-trial", **asdict(observation))
                self.record("trial-output", evaluation_id=evaluation_id, output=output,
                            output_hash=content_id(output))
                self._completed += 1
                self._failed_trials += int(status == "error")
        score = (sum(o.score for o in observations) / len(observations)
                 if all(o.status == "ok" for o in observations) else None)
        self.record("batch-evaluation", candidate_id=content_id(text), stage=stage,
                    score=score, observation_ids=[o.evaluation_id for o in observations])
        return BatchEvaluation(tuple(observations), score)

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
