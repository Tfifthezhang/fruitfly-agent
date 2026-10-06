"""Text capability facade: freezes a problem, injects services, delivers proposals."""
import asyncio
import json
from threading import Event
from uuid import uuid4

from .task_packs import TaskPackCatalog
from .search import OptimizationProblem, ObjectivePolicy, content_id
from .services import NativeSearchServices, SearchBudget, SearchJournal
from .text_optimizer import SearchPreview, TextProposal, SearchActivitySource
from .reporting import build_report


class HostedTextOptimizer:
    """Strategies only receive public contracts, never runtime or activation handles."""
    def __init__(self, strategy, config, workspace, parameters, *, target, label,
                 role_configs=None, services_factory=NativeSearchServices, task_source=None):
        if target is None:
            raise ValueError("selected optimization target is not enabled")
        if target.snapshot().schema not in strategy.supported_schemas:
            raise ValueError("optimizer does not support the selected target schema")
        if not strategy.required_capabilities <= services_factory.capabilities:
            raise ValueError("optimizer requires unavailable search capabilities")
        self.strategy, self.spec = strategy, strategy.spec
        self.config, self.workspace, self.target = config, workspace, target
        self.parameters, self.label = dict(parameters), label
        self.role_configs, self.services_factory = role_configs, services_factory
        self.task_source = task_source or TaskPackCatalog(workspace, legacy_path=parameters["cases_path"])
        self._stop = None
        self._services = None
        self._preview_suite = None
        self._last_progress = None

    def progress(self):
        if isinstance(self._services, SearchActivitySource):
            return self._services.progress()
        return self._last_progress

    def preview(self, *, task=None):
        # Execution uses the same immutable suite; changing a file requires a new preview.
        self._preview_suite = task or self._preview_suite or self.task_source.freeze(self.task_source.default_pack_id, self.parameters["target"])
        params = self.parameters
        return SearchPreview(self.spec.algorithm_id, self.label,
            "Authorized task cases, direction and search evidence are sent to the configured Provider; calls may incur cost. Trials have no tools or Session.",
            (("Cases", self._preview_suite.name),
             ("Training cases", str(len(self._preview_suite.train))),
             ("Selection validation cases", str(len(self._preview_suite.validation))),
             ("Maximum metric calls", str(params["max_metric_calls"])),
             ("Maximum model calls", str(params["max_model_calls"])),
             ("Maximum output tokens per call", str(params["output_max_tokens"])),
             ("Timeout seconds per operation", str(params["call_timeout_seconds"])),
             ("Trial model", self.config.model),
             ("Evaluation policy", self._preview_suite.policy_id),
             ("Code execution", self._preview_suite.evaluation_policy.execution_notice if self._preview_suite.evaluation_policy else "No generated code execution."),
             *((f"{role} model", cfg.model) for role, cfg in sorted((self.role_configs or {}).items()))),
            target_id=params["target"])

    async def search(self, prompt, direction, *, parent_manifest, task=None):
        if self._stop is not None:
            raise RuntimeError("a search is already running")
        suite = task or self._preview_suite or self.task_source.freeze(self.task_source.default_pack_id, self.parameters["target"])
        snapshot = self.target.snapshot()
        if snapshot.text != prompt:
            raise ValueError("target changed since host snapshot")
        self._last_progress = None
        search_id = uuid4().hex
        problem = OptimizationProblem(search_id, parent_manifest, snapshot, direction,
            suite.train, suite.validation, suite.digest,
            content_id(json.dumps({"parent": parent_manifest, "cases": suite.digest,
                                  "parameters": self.parameters, "task_execution_id": suite.execution_id}, sort_keys=True)),
            policy=ObjectivePolicy(suite.policy_id, suite.evaluation_policy.metric if suite.evaluation_policy else "accuracy"),
            parameters=tuple(sorted(self.parameters.items())))
        path = self.workspace / ".fruitfly" / "optimization" / "searches" / (search_id + ".jsonl")
        # Reject a relocated search root rather than writing outside the workspace.
        path.resolve().relative_to(self.workspace.resolve())
        budget = SearchBudget(self.parameters["max_model_calls"], self.parameters["max_metric_calls"])
        journal = SearchJournal(problem, path)
        self._stop = Event()
        try:
            policy_kwargs = {"scorer": suite.evaluation_policy.score} if suite.evaluation_policy is not None else {}
            services = self.services_factory(problem, self.config, self.target, budget=budget,
                journal=journal, stop=self._stop, timeout=self.parameters["call_timeout_seconds"],
                max_tokens=self.parameters["output_max_tokens"], role_configs=self.role_configs, **policy_kwargs)
            self._services = services
            journal.append("problem", baseline=snapshot.text, target_id=snapshot.target_id,
                           baseline_hash=snapshot.content_hash, direction=direction,
                           algorithm=self.spec.algorithm_id, implementation=self.spec.implementation_id,
                           parameters=dict(problem.parameters))
            journal.append('report-context', train_count=len(problem.train), validation_count=len(problem.validation),
                           metric=problem.policy.metric, objective_direction=problem.policy.direction)
            result = await self.strategy.search(problem, services)
            services.check()
            for candidate in result.candidates:
                self.target.validate(candidate.text)
            journal.append("search-result", status=result.stop_reason, usage=budget.used, exhausted_kind=budget.exhausted_kind,
                           candidates=[content_id(c.text) for c in result.candidates])
            history_digest = content_id(path.read_text(encoding="utf-8"))
            proposals = tuple(TextProposal(c.text, self.spec.algorithm_id, suite.digest,
                result.seed_score, c.score, budget.used["trial"],
                (*c.evidence, ("Evaluation policy", suite.policy_id), ("Task executor", suite.execution_id), ("Task package", suite.pack_id), ("Task package hash", suite.source_hash), ("Search history", str(path.relative_to(self.workspace))),
                 ("Search history hash", history_digest),
                 ("Stop reason", result.stop_reason), ("Model attempts", str(budget.used["model"]))),
                report=build_report(journal.rows, baseline_id=snapshot.content_hash, candidate_id=content_id(c.text),
                    train_count=len(problem.train), validation_count=len(problem.validation),
                    seed_score=result.seed_score, candidate_score=c.score,
                    metric=problem.policy.metric, direction=problem.policy.direction, stop_reason=result.stop_reason,
                    exhausted_kind=budget.exhausted_kind, model_calls=budget.used['model'], model_limit=budget.limits['model'],
                    trial_calls=budget.used['trial'], trial_limit=budget.limits['trial']))
                for c in sorted(result.candidates, key=lambda c: problem.policy.utility(c.score), reverse=True))
            return proposals
        except asyncio.CancelledError:
            self.cancel()
            journal.append("search-result", status="interrupted", usage=budget.used)
            raise
        except Exception as exc:
            journal.append("search-result", status="error", error=type(exc).__name__, usage=budget.used)
            raise
        finally:
            try:
                self._last_progress = self.progress()
            except Exception:
                self._last_progress = None
            self._stop = self._services = None
            self._preview_suite = None

    def cancel(self):
        if self._stop is None:
            return False
        self._stop.set()
        if self._services is not None:
            self._services.signal.set()
        return True

    def close(self):
        self.cancel()
