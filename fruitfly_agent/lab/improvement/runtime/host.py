"""Text capability facade: freezes a problem, injects services, delivers proposals."""
import asyncio
import json
from threading import Event
from uuid import uuid4

from fruitfly_agent.lab.improvement.tasks import TaskPackCatalog
from fruitfly_agent.lab.improvement.contracts.search import ImprovementProblem, ObjectivePolicy, content_id
from fruitfly_agent.lab.improvement.runtime.services import NativeSearchServices, SearchBudget, SearchJournal
from fruitfly_agent.lab.improvement.api import SearchPreview, TextProposal, SearchActivitySource, SearchCompletion
from fruitfly_agent.lab.improvement.runtime.reporting import build_report
from .workflow import run_search
from fruitfly_agent.lab.improvement.contracts.versions import SystemVersion
from fruitfly_agent.lab.improvement.contracts.candidates import VersionCandidate


class HostedTextImprover:
    """Strategies only receive public contracts, never runtime or activation handles."""
    def __init__(self, strategy, config, workspace, parameters, *, target, label,
                 role_configs=None, services_factory=NativeSearchServices, task_source=None, trial_targets=(),
                 confirm_on_holdout=False):
        if target is None:
            raise ValueError("selected improvement target is not enabled")
        if target.snapshot().schema not in strategy.supported_schemas:
            raise ValueError("improver does not support the selected target schema")
        if target.snapshot().role not in getattr(strategy, 'supported_roles', {'H'}):
            raise ValueError('improver does not support the selected H/S/I role')
        if not strategy.required_capabilities <= services_factory.capabilities:
            raise ValueError("improver requires unavailable search capabilities")
        if confirm_on_holdout and 'workflow-trials' not in services_factory.capabilities:
            raise ValueError('independent confirmation requires workflow trial services')
        self.strategy, self.spec = strategy, strategy.spec
        self.config, self.workspace, self.target = config, workspace, target
        self.parameters, self.label = dict(parameters), label
        self.role_configs, self.services_factory = role_configs, services_factory
        self.trial_targets = tuple(trial_targets)
        self.confirm_on_holdout = confirm_on_holdout
        self.task_source = task_source or TaskPackCatalog(workspace, legacy_path=parameters["cases_path"])
        self._stop = None
        self._services = None
        self._preview_suite = None
        self._last_progress = None
        self.method_usage = getattr(strategy, "usage", None)
        self.workflow = None
        self._prepared_workflow = None
        self._completion = None

    def completion(self):
        return self._completion

    def configure_workflow(self, workflow, *, role_configs=None):
        """Attach a generic workflow before use; construction starts no research."""
        if self._stop is not None or self._preview_suite is not None:
            raise RuntimeError("configure a workflow before previewing or running a search")
        if "workflow-trials" not in self.services_factory.capabilities:
            raise ValueError("automatic workflow requires workflow trial services")
        self.workflow = workflow
        self.role_configs = {**(self.role_configs or {}), **(role_configs or {})}

    def improvement_identity(self):
        from dataclasses import asdict
        return {"algorithm": self.spec.algorithm_id, "implementation": self.spec.implementation_id,
                "parameters": self.parameters,
                "workflow": self.workflow.implementation_id if self.workflow else None,
                "workflow_policy": asdict(self.workflow.policy) if self.workflow else None,
                "failure_processing": self.workflow.processor.implementation_id if self.workflow else None,
                "materials": self.strategy.source_identity() if callable(getattr(self.strategy, "source_identity", None)) else None}

    def experiment_target_id(self):
        return self.target.snapshot().target_id

    def experiment_available(self):
        return self.workflow is not None

    def experiment_timeout_seconds(self):
        if self.workflow is None:
            raise ValueError("benchmark improvement requires an automatic workflow")
        return self.workflow.policy.external_timeout_seconds

    def preview_experiment_plan(self, task_count):
        if self.workflow is None:
            raise ValueError("benchmark improvement requires a configured automatic workflow")
        if type(task_count) is not int or not 3 <= task_count <= 12:
            raise ValueError("benchmark improvement needs 3–12 tasks")
        policy = self.workflow.policy
        return SearchPreview(self.spec.algorithm_id, self.label,
            "Download and freeze the selected tasks, then run one bounded improvement job. "
            "Baseline, learning, candidates and confirmation share the displayed budgets. "
            "Model, network and container operations may incur cost. Adoption requires human review.",
            (("Method implementation", self.spec.implementation_id),
             ("Method parameters", json.dumps(self.parameters, sort_keys=True)),
             ("Trial model", self.config.model),
             *((f"{role} model", cfg.model) for role, cfg in sorted((self.role_configs or {}).items())),
             ("Independent confirmation", "Required before publishing a candidate"),
             ("Training cases", str(task_count - 2)), ("Selection cases", "1"), ("Independent cases", "1"),
             ("Maximum model calls", str(self.parameters["max_model_calls"])),
             ("Maximum task trials", str(self.parameters["max_metric_calls"])),
             ("Maximum output tokens per call", str(self.parameters["output_max_tokens"])),
             ("External task model allocation", str(policy.external_trial_model_calls)),
             ("External task timeout seconds", str(policy.external_trial_timeout_seconds)),
             ("Experiment deadline seconds", str(policy.external_timeout_seconds)),
             ("Minimum score gain", str(policy.min_improvement)),
             ("Maximum per-case regression", str(policy.max_case_regression)),
             ("Failure processing", self.workflow.processor.implementation_id)),
            target_id=self.experiment_target_id())

    def preview_experiment(self, context):
        from fruitfly_agent.lab.improvement.experiments.runner import BenchmarkTaskSource
        if self.workflow is None:
            raise ValueError("benchmark improvement requires a configured automatic workflow")
        if self._stop is not None:
            raise RuntimeError("an improvement job is already running")
        source = BenchmarkTaskSource(context.tasks)
        suite = source.freeze(source.default_pack_id, self.parameters["target"])
        prepared = self.workflow.prepare(suite, source)
        original = self.workflow.preview(suite, prepared)
        return SearchPreview(self.spec.algorithm_id, self.label,
            "This experiment runs original tasks, prepares material, searches candidates and confirms once. "
            "Container/model/network calls may incur cost. Adoption remains a separate decision.",
            (("Parent H/I/S", context.parent.version_id), ("Task set", context.tasks.digest),
             ("Training cases", str(len(context.tasks.train))), ("Selection cases", str(len(context.tasks.validation))),
             ("Maximum model calls", str(self.parameters["max_model_calls"])),
             ("Maximum task trials", str(self.parameters["max_metric_calls"])),
             ("External task model allocation", str(self.workflow.policy.external_trial_model_calls)),
             ("External task timeout seconds", str(self.workflow.policy.external_trial_timeout_seconds)),
             ("Experiment deadline seconds", str(self.workflow.policy.external_timeout_seconds)), *original),
            target_id=self.parameters["target"])

    async def search_experiment(self, context):
        from dataclasses import replace
        from fruitfly_agent.lab.improvement.automatic.workflow import AutomaticWorkflow
        from fruitfly_agent.lab.improvement.experiments.runner import BenchmarkTaskSource, BenchmarkSearchServices
        self.preview_experiment(context)
        host_policy = self.workflow.policy
        class ExternalServices(BenchmarkSearchServices):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs, context=context, policy=host_policy)
        previous = self.task_source, self.services_factory, self.workflow
        source = BenchmarkTaskSource(context.tasks)
        suite = source.freeze(source.default_pack_id, self.parameters["target"])
        self.task_source, self.services_factory = source, ExternalServices
        self.workflow = AutomaticWorkflow(self.workflow.processor,
            replace(host_policy, timeout_seconds=host_policy.external_timeout_seconds))
        try:
            proposals = await self.search(context.baseline, context.direction,
                parent_manifest=context.parent_manifest, task=suite)
            result = []
            for proposal in proposals:
                packet = context.packet_for_text(proposal.text)
                candidate = packet["candidate"]
                result.append(replace(proposal, evidence=(*proposal.evidence,
                    ("Parent system version", context.parent.version_id),
                    ("Candidate system version", SystemVersion.from_dict(candidate["version"]).version_id),
                    ("Version candidate", VersionCandidate.from_dict(candidate).candidate_id),
                    ("Original task source", context.original_evidence_id))))
            return tuple(result)
        finally:
            self.task_source, self.services_factory, self.workflow = previous

    def progress(self):
        if isinstance(self._services, SearchActivitySource):
            return self._services.progress()
        return self._last_progress

    def preview(self, *, task=None):
        # Execution uses the same immutable suite; changing a file requires a new preview.
        self._preview_suite = task or self._preview_suite or self.task_source.freeze(self.task_source.default_pack_id, self.parameters["target"])
        params = self.parameters
        material_details = ()
        if callable(getattr(self.strategy, 'check_materials', None)):
            material_details = self.strategy.check_materials(self._preview_suite, self.config) or ()
        workflow_details = ()
        if self.confirm_on_holdout:
            from .confirmation import freeze_confirmation
            confirmation = freeze_confirmation(self._preview_suite, self.task_source)
            material_details = (*material_details, ('Independent cases', str(len(confirmation))))
        if getattr(self, 'require_confirmation', False):
            confirmation = tuple(self.task_source.holdout(self._preview_suite.pack_id))
            if not confirmation:
                raise ValueError('this method requires an independent holdout task pack for real-search confirmation')
            self.strategy.confirmation_cases = confirmation
            material_details = (*material_details, ('Independent cases', str(len(confirmation))))
        if self.workflow is not None:
            self._prepared_workflow = self.workflow.prepare(self._preview_suite, self.task_source)
            workflow_details = self.workflow.preview(self._preview_suite, self._prepared_workflow)
        return SearchPreview(self.spec.algorithm_id, self.label,
            "Authorized task cases, direction and search evidence are sent to the configured Provider; calls may incur cost. "
            + ("Automatic search includes material preparation and independent confirmation; adoption requires human review."
               if self.workflow is not None else "Trials have no tools or Session."),
            (("Method implementation", self.spec.implementation_id),
             ("Method parameters", json.dumps(params, sort_keys=True)),
             ("Cases", self._preview_suite.name),
             ("Training cases", str(len(self._preview_suite.train))),
             ("Selection validation cases", str(len(self._preview_suite.validation))),
             ("Maximum metric calls", str(params["max_metric_calls"])),
             ("Maximum model calls", str(params["max_model_calls"])),
             ("Maximum output tokens per call", str(params["output_max_tokens"])),
             ("Timeout seconds per operation", str(params["call_timeout_seconds"])),
             ("Trial model", self.config.model),
             ("Independent confirmation", "Required before publishing a candidate"
              if self.workflow is not None or self.confirm_on_holdout or getattr(self, 'require_confirmation', False)
              else "Not provided; selection scores only"),
             ("Evaluation policy", self._preview_suite.policy_id),
             ("Code execution", self._preview_suite.evaluation_policy.execution_notice if self._preview_suite.evaluation_policy else "No generated code execution."),
             *((f"{role} model", cfg.model) for role, cfg in sorted((self.role_configs or {}).items())),
             *material_details,
             *(self.method_usage.details if self.method_usage is not None else ()),
             *workflow_details),
            target_id=params["target"], role=self.target.snapshot().role)

    async def search(self, prompt, direction, *, parent_manifest, task=None):
        if self._stop is not None:
            raise RuntimeError("a search is already running")
        self._completion = None
        suite = task or self._preview_suite or self.task_source.freeze(self.task_source.default_pack_id, self.parameters["target"])
        snapshot = self.target.snapshot()
        if snapshot.role not in getattr(self.strategy, 'supported_roles', {'H'}):
            raise ValueError('improver does not support the selected H/S/I role')
        if snapshot.text != prompt:
            raise ValueError("target changed since host snapshot")
        prepared = self.workflow.prepare(suite, self.task_source) if self.workflow is not None else None
        confirmation = ()
        if self.confirm_on_holdout:
            from .confirmation import freeze_confirmation
            confirmation = freeze_confirmation(suite, self.task_source)
        self._last_progress = None
        search_id = uuid4().hex
        problem = ImprovementProblem(search_id, parent_manifest, snapshot, direction,
            suite.train, suite.validation, suite.digest,
            content_id(json.dumps({"parent": parent_manifest, "cases": suite.digest,
                                  "parameters": self.parameters, "task_execution_id": suite.execution_id}, sort_keys=True)),
            policy=ObjectivePolicy(suite.policy_id, getattr(self.strategy, "objective_metric", suite.evaluation_policy.metric if suite.evaluation_policy else "accuracy")),
            parameters=tuple(sorted(self.parameters.items())), task_execution_id=suite.execution_id)
        path = self.workspace / ".fruitfly" / "improvement" / "searches" / (search_id + ".jsonl")
        # Reject a relocated search root rather than writing outside the workspace.
        path.resolve().relative_to(self.workspace.resolve())
        budget = SearchBudget(self.parameters["max_model_calls"], self.parameters["max_metric_calls"])
        journal = SearchJournal(problem, path)
        self._stop = Event()
        final_reason, proposals, seed_score = 'error', (), None
        try:
            policy_kwargs = {"scorer": suite.evaluation_policy.score} if suite.evaluation_policy is not None else {}
            if self.trial_targets:
                policy_kwargs['trial_targets'] = self.trial_targets
            services = self.services_factory(problem, self.config, self.target, budget=budget,
                journal=journal, stop=self._stop, timeout=self.parameters["call_timeout_seconds"],
                max_tokens=self.parameters["output_max_tokens"], role_configs=self.role_configs, **policy_kwargs)
            self._services = services
            journal.append("problem", baseline=snapshot.text, target_id=snapshot.target_id,
                           role=snapshot.role,
                           baseline_hash=snapshot.content_hash, direction=direction,
                           algorithm=self.spec.algorithm_id, implementation=self.spec.implementation_id,
                           parameters=dict(problem.parameters))
            journal.append('report-context', train_count=len(problem.train), validation_count=len(problem.validation),
                           metric=problem.policy.metric, objective_direction=problem.policy.direction)
            if self.workflow is not None:
                journal.append("workflow", implementation=self.workflow.implementation_id,
                               material_source_hash=prepared.source_hash)
            result = await run_search(self.strategy, problem, services,
                controller=self.workflow, prepared=prepared)
            if self.confirm_on_holdout:
                from .confirmation import confirm_result
                result = await confirm_result(problem, services, result, confirmation, policy=suite.evaluation_policy)
            final_reason, seed_score = result.stop_reason, result.seed_score
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
            services.check_cancellation()
            return proposals
        except asyncio.CancelledError:
            final_reason = 'interrupted'
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
            report = proposals[0].report if proposals else build_report(
                journal.rows, baseline_id=snapshot.content_hash, candidate_id='',
                train_count=len(problem.train), validation_count=len(problem.validation),
                seed_score=seed_score, metric=problem.policy.metric, direction=problem.policy.direction,
                stop_reason=final_reason, exhausted_kind=budget.exhausted_kind,
                model_calls=budget.used['model'], model_limit=budget.limits['model'],
                trial_calls=budget.used['trial'], trial_limit=budget.limits['trial'])
            self._completion = SearchCompletion(report, (
                ('Search history', str(path.relative_to(self.workspace))),
                ('Search history hash', content_id(path.read_text(encoding='utf-8')))))
            self._stop = self._services = None
            self._preview_suite = None
            self._prepared_workflow = None

    def cancel(self):
        if self._stop is None:
            return False
        self._stop.set()
        if self._services is not None:
            self._services.signal.set()
        return True

    def close(self):
        self.cancel()
